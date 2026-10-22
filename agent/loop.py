import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

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
from agent.llm_client import ResilientLLMClient, ToolCall
from escalation.handoff import EscalationReport


class IncidentResponseAgent:
    """
    Pure Python Autonomous Incident Response Agent.
    Implements a Diagnose -> Act -> Verify loop with deterministic safety guardrails.
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
        """Registers diagnosis and remediation tools bound to current environment."""
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
        return {tool.name: tool for tool in tools}

    def run(self, env: MockEnvironment, alert: AlertEvent) -> IncidentSessionState:
        """
        Runs the full autonomous diagnose-act-verify loop on the triggered alert.
        """
        tool_registry = self._build_tools_registry(env)
        openai_tools = [tool.to_openai_tool() for tool in tool_registry.values()]

        session = IncidentSessionState(
            alert_id=alert.alert_id,
            target_service=alert.service,
            max_steps=self.max_steps,
        )

        # Initialize conversation messages
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

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": alert_context},
        ]

        action_proposals_history: List[ActionProposal] = []
        is_external_dependency = False

        while session.status == SessionStatus.IN_PROGRESS and session.step_count < session.max_steps:
            session.step_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Call LLM
            response = self.llm_client.generate_with_tools(messages=messages, tools=openai_tools)

            # If LLM did not call any tools, it is providing conclusions/final thoughts
            if not response.tool_calls:
                session.final_diagnosis = response.content or "No explanation provided."
                
                # Check whether the service is recovered or needs escalation
                if env.is_service_recovered(session.target_service):
                    session.status = SessionStatus.RESOLVED
                else:
                    session.status = SessionStatus.ESCALATED

                session.trace.append(
                    StepTrace(
                        step_number=session.step_count,
                        thought=response.content,
                        timestamp=now_str,
                    )
                )
                break

            # Process tool calls
            # Append assistant message with tool calls to context
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
            messages.append(assistant_msg)

            for tc in response.tool_calls:
                tool_name = tc.name
                tool_args = tc.arguments
                tool = tool_registry.get(tool_name)

                if not tool:
                    obs = {"error": f"Tool '{tool_name}' is not registered."}
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(obs)})
                    continue

                is_remediation = tool_name in ["restart_service", "rollback_deployment", "scale_replicas", "clear_cache"]

                if not is_remediation:
                    # Diagnosis Tool Execution
                    obs = tool.execute(**tool_args)

                    # Update session diagnostic telemetry flags
                    if tool_name == "query_logs":
                        session.logs_inspected = True
                        if isinstance(obs, list):
                            errors = [e for e in obs if e.get("level") in ("ERROR", "CRITICAL")]
                            session.matching_log_errors += len(errors)
                            # Check if log messages reveal external third-party issues
                            for e in obs:
                                msg_lower = e.get("message", "").lower()
                                if "stripe" in msg_lower or "upstream vendor" in msg_lower or "third-party" in msg_lower or "external provider" in msg_lower:
                                    is_external_dependency = True

                    elif tool_name in ("check_service_status", "get_metrics"):
                        session.metrics_inspected = True
                    elif tool_name == "get_deployment_history":
                        session.deployments_inspected = True

                    session.trace.append(
                        StepTrace(
                            step_number=session.step_count,
                            thought=response.content,
                            tool_called=tool_name,
                            tool_arguments=tool_args,
                            observation=obs,
                            timestamp=now_str,
                        )
                    )

                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(obs)})

                else:
                    # Remediation Tool Proposal -> Check Deterministic Guardrails
                    target_svc = tool_args.get("service_name", session.target_service)
                    proposal = ActionProposal(
                        action_name=tool_name,
                        service_name=target_svc,
                        arguments=tool_args,
                    )

                    guardrail_eval = self.guardrail_engine.evaluate_proposal(
                        proposal=proposal,
                        env=env,
                        session_action_history=action_proposals_history,
                    )

                    if not guardrail_eval.allowed:
                        # VETOED by Deterministic Rule Engine
                        obs = {
                            "status": "VETOED",
                            "allowed": False,
                            "policy": guardrail_eval.policy_name,
                            "reason": guardrail_eval.reason,
                            "guidance": "Do not attempt this action again. Escalate to human operator.",
                        }
                        session.trace.append(
                            StepTrace(
                                step_number=session.step_count,
                                thought=response.content,
                                tool_called=tool_name,
                                tool_arguments=tool_args,
                                guardrail_decision="VETOED",
                                observation=obs,
                                timestamp=now_str,
                            )
                        )
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(obs)})
                    else:
                        # ALLOWED by Guardrail Engine -> Execute Mutation
                        action_proposals_history.append(proposal)
                        exec_result = tool.execute(**tool_args)

                        # Post-Action Health Verification
                        is_healthy = env.is_service_recovered(target_svc)
                        verification_msg = (
                            "Service health verified: RECOVERED (Metrics normalized)."
                            if is_healthy
                            else "Service health check: NOT RECOVERED. Problem persists."
                        )

                        obs = {
                            "action_result": exec_result,
                            "guardrail_status": "ALLOWED",
                            "verification": verification_msg,
                            "is_healthy": is_healthy,
                        }

                        session.actions_attempted.append({
                            "action": tool_name,
                            "service": target_svc,
                            "success": exec_result.get("success", False),
                            "message": exec_result.get("message", ""),
                            "is_healthy_after": is_healthy,
                        })

                        session.trace.append(
                            StepTrace(
                                step_number=session.step_count,
                                thought=response.content,
                                tool_called=tool_name,
                                tool_arguments=tool_args,
                                guardrail_decision="ALLOWED",
                                observation=obs,
                                timestamp=now_str,
                            )
                        )
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(obs)})

                        if is_healthy:
                            session.status = SessionStatus.RESOLVED
                            # Prompt the agent for final conclusion / post-remediation diagnosis
                            try:
                                final_resp = self.llm_client.generate_with_tools(messages=messages, tools=[])
                                if final_resp and final_resp.content:
                                    session.final_diagnosis = final_resp.content
                                    session.trace.append(
                                        StepTrace(
                                            step_number=session.step_count + 1,
                                            thought=final_resp.content,
                                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        )
                                    )
                                    session.step_count += 1
                            except Exception:
                                pass
                            if not session.final_diagnosis:
                                session.final_diagnosis = response.content or "Service health successfully verified and recovered."

        # Check for loop step budget exhaustion
        if session.step_count >= session.max_steps and session.status == SessionStatus.IN_PROGRESS:
            session.status = SessionStatus.MAX_STEPS_EXCEEDED

        # Calculate final objective confidence score
        failed_count = sum(1 for a in session.actions_attempted if not a.get("is_healthy_after", False))
        session.confidence_score = ConfidenceEvaluator.calculate_confidence(
            hypothesis=session.final_diagnosis or "",
            logs_inspected=session.logs_inspected,
            deployments_inspected=session.deployments_inspected,
            metrics_inspected=session.metrics_inspected,
            matching_log_errors=session.matching_log_errors,
            failed_mutations_count=failed_count,
            is_external_dependency=is_external_dependency,
        )

        # If escalated or steps exceeded, produce human handoff packet
        if session.status in (SessionStatus.ESCALATED, SessionStatus.MAX_STEPS_EXCEEDED) or not env.is_service_recovered(session.target_service):
            session.status = SessionStatus.ESCALATED
            session.escalation_report = EscalationReport(
                incident_id=alert.alert_id,
                target_service=session.target_service,
                escalation_reason=(
                    "External 3rd-party outage detected"
                    if is_external_dependency
                    else "Autonomous actions exhausted, vetoed, or ineffective."
                ),
                severity=alert.severity,
                diagnosed_hypothesis=session.final_diagnosis or "Indeterminate root cause.",
                confidence_score=session.confidence_score,
                actions_attempted=session.actions_attempted,
                unresolved_symptoms=[
                    f"Service '{session.target_service}' remains in unhealthy state",
                    f"Active alert: {alert.alert_type} ({alert.summary})",
                ],
                recommended_human_action=(
                    "Check external vendor status page (e.g. Stripe status) and wait for vendor restoration."
                    if is_external_dependency
                    else "Review application stack trace and manually inspect container metrics."
                ),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        return session
