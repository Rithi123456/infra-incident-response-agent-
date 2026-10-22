import json
from datetime import datetime
from typing import Dict, Any, List, Optional, TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END
from mock_infra.environment import MockEnvironment
from mock_infra.models import AlertEvent
from tools.base import Tool
from tools.diagnosis import (
    CheckServiceStatusTool,
    GetMetricsTool,
    QueryLogsTool,
    GetDeploymentHistoryTool,
)
from tools.remediation import (
    RestartServiceTool,
    RollbackDeploymentTool,
    ScaleReplicasTool,
    ClearCacheTool,
)
from guardrails.engine import GuardrailEngine
from guardrails.policies import ActionProposal
from agent.state import IncidentSessionState, SessionStatus, StepTrace
from agent.confidence import ConfidenceEvaluator
from agent.prompts import SYSTEM_PROMPT
from agent.llm_client import ResilientLLMClient
from escalation.handoff import EscalationReport


class GraphState(TypedDict):
    alert_id: str
    target_service: str
    alert_summary: str
    severity: str
    step_count: int
    max_steps: int
    status: str  # "IN_PROGRESS", "RESOLVED", "ESCALATED"
    messages: List[Dict[str, Any]]
    actions_attempted: List[Dict[str, Any]]
    action_proposals_history: List[ActionProposal]
    pending_proposal: Optional[ActionProposal]
    guardrail_decision: Optional[str]  # "ALLOWED" or "VETOED"
    guardrail_reason: Optional[str]
    is_external_dependency: bool
    logs_inspected: bool
    metrics_inspected: bool
    deployments_inspected: bool
    matching_log_errors: int
    final_diagnosis: Optional[str]
    confidence_score: float
    escalation_report: Optional[EscalationReport]
    trace: List[StepTrace]


class LangGraphIncidentAgent:
    """
    LangGraph StateGraph orchestration layer for the Incident Response Agent.
    Maps state transitions into explicit nodes (Diagnose, Guardrail, Remediate, Verify, Escalate)
    and conditional branching edges.
    """

    def __init__(
        self,
        llm_client: ResilientLLMClient,
        guardrail_engine: Optional[GuardrailEngine] = None,
        max_steps: int = 8,
    ):
        self.llm_client = llm_client
        self.guardrail_engine = guardrail_engine or GuardrailEngine()
        self.max_steps = max_steps

    def _build_tools_registry(self, env: MockEnvironment) -> Dict[str, Tool]:
        tools: List[Tool] = [
            CheckServiceStatusTool(env),
            GetMetricsTool(env),
            QueryLogsTool(env),
            GetDeploymentHistoryTool(env),
            RestartServiceTool(env),
            RollbackDeploymentTool(env),
            ScaleReplicasTool(env),
            ClearCacheTool(env),
        ]
        return {t.name: t for t in tools}

    def compile_graph(self, env: MockEnvironment):
        """Builds and compiles the LangGraph StateGraph bound to the environment."""
        tool_registry = self._build_tools_registry(env)
        openai_tools = [t.to_openai_tool() for t in tool_registry.values()]

        # -------------------------------------------------------------
        # Graph Nodes
        # -------------------------------------------------------------

        def diagnose_and_decide(state: GraphState) -> Dict[str, Any]:
            step_count = state["step_count"] + 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            response = self.llm_client.generate_with_tools(
                messages=state["messages"],
                tools=openai_tools,
            )

            # If LLM stopped calling tools
            if not response.tool_calls:
                diagnosis = response.content or "No explanation provided."
                is_healthy = env.is_service_recovered(state["target_service"])
                new_status = "RESOLVED" if is_healthy else "ESCALATED"

                trace_entry = StepTrace(
                    step_number=step_count,
                    thought=response.content,
                    timestamp=now_str,
                )
                return {
                    "step_count": step_count,
                    "final_diagnosis": diagnosis,
                    "status": new_status,
                    "trace": state["trace"] + [trace_entry],
                    "pending_proposal": None,
                }

            # LLM called tool(s)
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if response.content:
                assistant_msg["content"] = response.content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in response.tool_calls
            ]
            new_messages = list(state["messages"]) + [assistant_msg]
            new_trace = list(state["trace"])

            logs_flag = state["logs_inspected"]
            metrics_flag = state["metrics_inspected"]
            deploy_flag = state["deployments_inspected"]
            matching_errors = state["matching_log_errors"]
            is_ext = state["is_external_dependency"]
            pending_prop = None

            for tc in response.tool_calls:
                tool_name = tc.name
                tool_args = tc.arguments
                tool = tool_registry.get(tool_name)

                if not tool:
                    err_obs = {"error": f"Tool '{tool_name}' not registered."}
                    new_messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(err_obs)})
                    continue

                if tool_name in ["restart_service", "rollback_deployment", "scale_replicas", "clear_cache"]:
                    # Route to Guardrail Node
                    target_svc = tool_args.get("service_name", state["target_service"])
                    pending_prop = ActionProposal(
                        action_name=tool_name,
                        service_name=target_svc,
                        arguments=tool_args,
                    )
                else:
                    # Execute Diagnosis Tool Immediately
                    obs = tool.execute(**tool_args)

                    if tool_name == "query_logs":
                        logs_flag = True
                        if isinstance(obs, list):
                            errors = [e for e in obs if e.get("level") in ("ERROR", "CRITICAL")]
                            matching_errors += len(errors)
                            for e in obs:
                                msg_lower = e.get("message", "").lower()
                                if "stripe" in msg_lower or "upstream vendor" in msg_lower or "third-party" in msg_lower or "external provider" in msg_lower:
                                    is_ext = True
                    elif tool_name in ("check_service_status", "get_metrics"):
                        metrics_flag = True
                    elif tool_name == "get_deployment_history":
                        deploy_flag = True

                    new_trace.append(
                        StepTrace(
                            step_number=step_count,
                            thought=response.content,
                            tool_called=tool_name,
                            tool_arguments=tool_args,
                            observation=obs,
                            timestamp=now_str,
                        )
                    )
                    new_messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(obs)})

            return {
                "step_count": step_count,
                "messages": new_messages,
                "trace": new_trace,
                "pending_proposal": pending_prop,
                "logs_inspected": logs_flag,
                "metrics_inspected": metrics_flag,
                "deployments_inspected": deploy_flag,
                "matching_log_errors": matching_errors,
                "is_external_dependency": is_ext,
            }

        def guardrail_gate(state: GraphState) -> Dict[str, Any]:
            """NON-LLM deterministic security node in the LangGraph graph."""
            prop = state["pending_proposal"]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            eval_res = self.guardrail_engine.evaluate_proposal(
                proposal=prop,
                env=env,
                session_action_history=state["action_proposals_history"],
            )

            new_trace = list(state["trace"])
            new_messages = list(state["messages"])

            if not eval_res.allowed:
                obs = {
                    "status": "VETOED",
                    "allowed": False,
                    "policy": eval_res.policy_name,
                    "reason": eval_res.reason,
                    "guidance": "Action blocked by safety policy. Escalate to human operator.",
                }
                new_trace.append(
                    StepTrace(
                        step_number=state["step_count"],
                        thought="Guardrail evaluation",
                        tool_called=prop.action_name,
                        tool_arguments=prop.arguments,
                        guardrail_decision="VETOED",
                        observation=obs,
                        timestamp=now_str,
                    )
                )
                new_messages.append({
                    "role": "tool",
                    "tool_call_id": f"guard_{state['step_count']}",
                    "content": json.dumps(obs),
                })
                return {
                    "guardrail_decision": "VETOED",
                    "guardrail_reason": eval_res.reason,
                    "trace": new_trace,
                    "messages": new_messages,
                }
            else:
                return {
                    "guardrail_decision": "ALLOWED",
                    "guardrail_reason": eval_res.reason,
                }

        def execute_remediation(state: GraphState) -> Dict[str, Any]:
            """Executes mutation allowed by guardrail."""
            prop = state["pending_proposal"]
            tool = tool_registry[prop.action_name]
            exec_res = tool.execute(**prop.arguments)

            history = list(state["action_proposals_history"]) + [prop]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            is_healthy = env.is_service_recovered(prop.service_name)
            action_record = {
                "action": prop.action_name,
                "service": prop.service_name,
                "success": exec_res.get("success", False),
                "message": exec_res.get("message", ""),
                "is_healthy_after": is_healthy,
            }

            obs = {
                "action_result": exec_res,
                "guardrail_status": "ALLOWED",
                "is_healthy": is_healthy,
            }

            new_trace = list(state["trace"]) + [
                StepTrace(
                    step_number=state["step_count"],
                    tool_called=prop.action_name,
                    tool_arguments=prop.arguments,
                    guardrail_decision="ALLOWED",
                    observation=obs,
                    timestamp=now_str,
                )
            ]
            new_messages = list(state["messages"]) + [
                {"role": "tool", "tool_call_id": f"exec_{state['step_count']}", "content": json.dumps(obs)}
            ]

            return {
                "actions_attempted": state["actions_attempted"] + [action_record],
                "action_proposals_history": history,
                "pending_proposal": None,
                "trace": new_trace,
                "messages": new_messages,
            }

        def verify_health(state: GraphState) -> Dict[str, Any]:
            """Verifies target service telemetry and updates resolution status."""
            is_healthy = env.is_service_recovered(state["target_service"])
            if is_healthy:
                return {"status": "RESOLVED"}
            else:
                return {"status": "IN_PROGRESS"}

        def escalate(state: GraphState) -> Dict[str, Any]:
            """Generates structured human SRE handoff memo."""
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            failed_count = sum(1 for a in state["actions_attempted"] if not a.get("is_healthy_after", False))

            score = ConfidenceEvaluator.calculate_confidence(
                hypothesis=state["final_diagnosis"] or "",
                logs_inspected=state["logs_inspected"],
                deployments_inspected=state["deployments_inspected"],
                metrics_inspected=state["metrics_inspected"],
                matching_log_errors=state["matching_log_errors"],
                failed_mutations_count=failed_count,
                is_external_dependency=state["is_external_dependency"],
            )

            report = EscalationReport(
                incident_id=state["alert_id"],
                target_service=state["target_service"],
                escalation_reason=(
                    "External 3rd-party outage detected"
                    if state["is_external_dependency"]
                    else "Autonomous actions exhausted, vetoed, or ineffective."
                ),
                severity=state["severity"],
                diagnosed_hypothesis=state["final_diagnosis"] or "Guardrail veto or unresolved incident.",
                confidence_score=score,
                actions_attempted=state["actions_attempted"],
                unresolved_symptoms=[f"Service '{state['target_service']}' remains unhealthy"],
                recommended_human_action="Review application stack trace and manually inspect container metrics.",
                timestamp=now_str,
            )

            return {
                "status": "ESCALATED",
                "confidence_score": score,
                "escalation_report": report,
            }

        # -------------------------------------------------------------
        # Conditional Edge Routing Functions
        # -------------------------------------------------------------

        def route_after_diagnose(state: GraphState) -> str:
            if state["status"] == "RESOLVED":
                return END
            if state["status"] == "ESCALATED":
                return "escalate"
            if state["pending_proposal"]:
                return "guardrail_gate"
            if state["step_count"] >= state["max_steps"]:
                return "escalate"
            return "diagnose_and_decide"

        def route_after_guardrail(state: GraphState) -> str:
            if state["guardrail_decision"] == "ALLOWED":
                return "execute_remediation"
            else:
                # If vetoed by Tier-1 or budget exhausted, escalate immediately
                return "escalate"

        def route_after_verify(state: GraphState) -> str:
            if state["status"] == "RESOLVED":
                return END
            if state["step_count"] >= state["max_steps"] or len(state["actions_attempted"]) >= 2:
                return "escalate"
            return "diagnose_and_decide"

        # -------------------------------------------------------------
        # Graph Construction
        # -------------------------------------------------------------
        builder = StateGraph(GraphState)

        builder.add_node("diagnose_and_decide", diagnose_and_decide)
        builder.add_node("guardrail_gate", guardrail_gate)
        builder.add_node("execute_remediation", execute_remediation)
        builder.add_node("verify_health", verify_health)
        builder.add_node("escalate", escalate)

        builder.set_entry_point("diagnose_and_decide")

        builder.add_conditional_edges(
            "diagnose_and_decide",
            route_after_diagnose,
            {
                "guardrail_gate": "guardrail_gate",
                "diagnose_and_decide": "diagnose_and_decide",
                "escalate": "escalate",
                END: END,
            },
        )

        builder.add_conditional_edges(
            "guardrail_gate",
            route_after_guardrail,
            {
                "execute_remediation": "execute_remediation",
                "escalate": "escalate",
            },
        )

        builder.add_edge("execute_remediation", "verify_health")

        builder.add_conditional_edges(
            "verify_health",
            route_after_verify,
            {
                "diagnose_and_decide": "diagnose_and_decide",
                "escalate": "escalate",
                END: END,
            },
        )

        builder.add_edge("escalate", END)

        return builder.compile()

    def run(self, env: MockEnvironment, alert: AlertEvent) -> IncidentSessionState:
        """
        Executes the compiled LangGraph graph and returns an IncidentSessionState.
        """
        graph = self.compile_graph(env)

        alert_context = (
            f"NEW INCIDENT ALERT TRIGGERED:\n"
            f"- Alert ID: {alert.alert_id}\n"
            f"- Target Service: {alert.service}\n"
            f"- Alert Type: {alert.alert_type}\n"
            f"- Severity: {alert.severity}\n"
            f"- Metric Trigger: {alert.trigger_metric} = {alert.trigger_value} (Threshold: {alert.threshold})\n"
            f"- Summary: {alert.summary}\n\n"
            f"Begin diagnosis immediately. Inspect logs, metrics, and deployments before deciding."
        )

        initial_state: GraphState = {
            "alert_id": alert.alert_id,
            "target_service": alert.service,
            "alert_summary": alert.summary,
            "severity": str(alert.severity),
            "step_count": 0,
            "max_steps": self.max_steps,
            "status": "IN_PROGRESS",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": alert_context},
            ],
            "actions_attempted": [],
            "action_proposals_history": [],
            "pending_proposal": None,
            "guardrail_decision": None,
            "guardrail_reason": None,
            "is_external_dependency": False,
            "logs_inspected": False,
            "metrics_inspected": False,
            "deployments_inspected": False,
            "matching_log_errors": 0,
            "final_diagnosis": None,
            "confidence_score": 0.0,
            "escalation_report": None,
            "trace": [],
        }

        final_output = graph.invoke(initial_state)

        # Compute confidence score if resolved
        failed_count = sum(1 for a in final_output["actions_attempted"] if not a.get("is_healthy_after", False))
        conf_score = ConfidenceEvaluator.calculate_confidence(
            hypothesis=final_output["final_diagnosis"] or "",
            logs_inspected=final_output["logs_inspected"],
            deployments_inspected=final_output["deployments_inspected"],
            metrics_inspected=final_output["metrics_inspected"],
            matching_log_errors=final_output["matching_log_errors"],
            failed_mutations_count=failed_count,
            is_external_dependency=final_output["is_external_dependency"],
        )

        status_enum = SessionStatus(final_output["status"])

        return IncidentSessionState(
            alert_id=final_output["alert_id"],
            target_service=final_output["target_service"],
            status=status_enum,
            step_count=final_output["step_count"],
            max_steps=self.max_steps,
            logs_inspected=final_output["logs_inspected"],
            metrics_inspected=final_output["metrics_inspected"],
            deployments_inspected=final_output["deployments_inspected"],
            matching_log_errors=final_output["matching_log_errors"],
            actions_attempted=final_output["actions_attempted"],
            trace=final_output["trace"],
            final_diagnosis=final_output["final_diagnosis"],
            confidence_score=conf_score,
            escalation_report=final_output["escalation_report"],
        )

    def get_mermaid_graph(self, env: Optional[MockEnvironment] = None) -> str:
        """Returns the Mermaid syntax diagram of the LangGraph graph."""
        e = env or MockEnvironment()
        graph = self.compile_graph(e)
        return graph.get_graph().draw_mermaid()
