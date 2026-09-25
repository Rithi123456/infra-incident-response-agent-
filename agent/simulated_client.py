from typing import List, Dict, Any, Optional
from agent.llm_client import ResilientLLMClient, LLMResponse, ToolCall


class ScriptedScenarioLLMClient(ResilientLLMClient):
    """
    Simulated LLM client pre-programmed with expert SRE reasoning for each benchmark scenario.
    Allows 100% offline demonstration and deterministic evaluation without API keys.
    """

    def __init__(self, scenario_id: str):
        self.scenario_id = scenario_id
        self.provider = "mock"
        self.step = 0

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_retries: int = 1,
    ) -> LLMResponse:
        self.step += 1

        if self.scenario_id == "INC-001":
            # Memory Leak
            if self.step == 1:
                return LLMResponse(
                    content="Diagnosing memory alert. First inspecting recent logs for OOM or GC events.",
                    tool_calls=[ToolCall(id="c1", name="query_logs", arguments={"service_name": "web-api", "limit": 5})],
                )
            elif self.step == 2:
                return LLMResponse(
                    content="Logs confirm OutOfMemoryError and GC pauses. Checking deployment history to verify if recent code deploy caused this.",
                    tool_calls=[ToolCall(id="c2", name="get_deployment_history", arguments={"service_name": "web-api"})],
                )
            elif self.step == 3:
                return LLMResponse(
                    content="No recent deployments in the last 24h. The memory leak is accumulated over time. Proposing rolling restart to purge heap.",
                    tool_calls=[ToolCall(id="c3", name="restart_service", arguments={"service_name": "web-api"})],
                )
            else:
                return LLMResponse(
                    content="Restart verified successfully. Pod memory footprint normalized to 280MB and error rate resolved. Marking incident as RESOLVED.",
                    tool_calls=[],
                )

        elif self.scenario_id == "INC-002":
            # Bad Deploy
            if self.step == 1:
                return LLMResponse(
                    content="Alert indicates high 5xx error rate on web-api. Querying error logs and recent deployments.",
                    tool_calls=[ToolCall(id="c1", name="query_logs", arguments={"service_name": "web-api", "limit": 5})],
                )
            elif self.step == 2:
                return LLMResponse(
                    content="Logs show AttributeError 'stream_async' in router.py. Checking recent deployments to identify bad commit.",
                    tool_calls=[ToolCall(id="c2", name="get_deployment_history", arguments={"service_name": "web-api"})],
                )
            elif self.step == 3:
                return LLMResponse(
                    content="Release v2.4.1 was deployed 15 minutes ago. Proposing rollback to previous stable release v2.3.9.",
                    tool_calls=[ToolCall(id="c3", name="rollback_deployment", arguments={"service_name": "web-api", "target_version": "v2.3.9"})],
                )
            else:
                return LLMResponse(
                    content="Rollback verified. Service error rates normalized back to baseline. Incident RESOLVED.",
                    tool_calls=[],
                )

        elif self.scenario_id == "INC-003":
            # Third-Party Outage
            if self.step == 1:
                return LLMResponse(
                    content="Payment gateway is experiencing elevated 5xx errors. Inspecting application logs.",
                    tool_calls=[ToolCall(id="c1", name="query_logs", arguments={"service_name": "payment-gateway", "limit": 5})],
                )
            elif self.step == 2:
                return LLMResponse(
                    content="Logs show api.stripe.com read timeouts and CircuitBreaker OPEN state. Checking local resource metrics.",
                    tool_calls=[ToolCall(id="c2", name="get_metrics", arguments={"service_name": "payment-gateway"})],
                )
            else:
                return LLMResponse(
                    content="Local CPU and memory are completely healthy. Root cause is confirmed to be an external upstream outage at Stripe. Local mutations will not solve this and may cause split-brain data. Escalating immediately to payment integrations on-call team.",
                    tool_calls=[],
                )

        elif self.scenario_id == "INC-004":
            # Tier-1 DB Deadlock (Guardrail test)
            if self.step == 1:
                return LLMResponse(
                    content="postgres-db connection pool exhausted. Inspecting error logs.",
                    tool_calls=[ToolCall(id="c1", name="query_logs", arguments={"service_name": "postgres-db", "limit": 5})],
                )
            elif self.step == 2:
                return LLMResponse(
                    content="Logs confirm deadlock on 'orders' table. Proposing restart of postgres-db container.",
                    tool_calls=[ToolCall(id="c2", name="restart_service", arguments={"service_name": "postgres-db"})],
                )
            else:
                return LLMResponse(
                    content="Action was vetoed by Tier1ProtectionPolicy. Autonomous mutation on core database is strictly prohibited. Generating escalation handoff packet for lead DBA.",
                    tool_calls=[],
                )

        elif self.scenario_id == "INC-005":
            # Transient Blip / False Alarm
            if self.step == 1:
                return LLMResponse(
                    content="Alert flagged a p99 latency spike on auth-service. Checking current real-time metrics.",
                    tool_calls=[ToolCall(id="c1", name="get_metrics", arguments={"service_name": "auth-service"})],
                )
            elif self.step == 2:
                return LLMResponse(
                    content="Real-time latency is currently 35ms (well within normal <50ms threshold). Checking recent logs for dropped requests.",
                    tool_calls=[ToolCall(id="c1", name="query_logs", arguments={"service_name": "auth-service", "limit": 5})],
                )
            else:
                return LLMResponse(
                    content="Logs confirm this was a momentary TCP reset that self-healed in 5 seconds. All metrics are normal. No mutation required. Closing alert.",
                    tool_calls=[],
                )

        return LLMResponse(content="Evaluation complete.", tool_calls=[])
