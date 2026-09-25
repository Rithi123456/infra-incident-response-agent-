import pytest
from mock_infra.environment import MockEnvironment
from mock_infra.scenarios import inject_scenario
from agent.llm_client import ResilientLLMClient, LLMResponse, ToolCall
from agent.loop import IncidentResponseAgent
from agent.state import SessionStatus


class ScriptedMockLLMClient(ResilientLLMClient):
    """A scripted mock LLM client for deterministic testing of the loop."""

    def __init__(self, script):
        self.script = script
        self.call_count = 0
        self.provider = "mock"

    def generate_with_tools(self, messages, tools, max_retries=1):
        if self.call_count < len(self.script):
            res = self.script[self.call_count]
            self.call_count += 1
            return res
        return LLMResponse(content="Final step reached.")


def test_agent_memory_leak_success_path():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-001")

    # Scripted sequence:
    # 1. query_logs
    # 2. restart_service("web-api")
    # 3. conclusion text
    script = [
        LLMResponse(
            content="Checking logs to identify root cause.",
            tool_calls=[ToolCall(id="c1", name="query_logs", arguments={"service_name": "web-api", "limit": 5})],
        ),
        LLMResponse(
            content="Logs show OOM heap exhaustion. Proposing service restart.",
            tool_calls=[ToolCall(id="c2", name="restart_service", arguments={"service_name": "web-api"})],
        ),
        LLMResponse(
            content="Restart verified. Memory back to normal. Incident resolved autonomously.",
            tool_calls=[],
        ),
    ]

    mock_llm = ScriptedMockLLMClient(script)
    agent = IncidentResponseAgent(llm_client=mock_llm)

    session = agent.run(env, alert)

    assert session.status == SessionStatus.RESOLVED
    assert session.logs_inspected is True
    assert len(session.actions_attempted) == 1
    assert session.actions_attempted[0]["success"] is True
    assert session.actions_attempted[0]["is_healthy_after"] is True
    assert env.is_service_recovered("web-api") is True
    assert session.confidence_score > 0.5


def test_agent_tier1_guardrail_veto_and_escalate():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-004")  # Tier-1 postgres deadlock

    # Scripted sequence:
    # 1. Propose restart on postgres-db
    # 2. Conclude and escalate after veto
    script = [
        LLMResponse(
            content="Attempting restart on postgres-db.",
            tool_calls=[ToolCall(id="c1", name="restart_service", arguments={"service_name": "postgres-db"})],
        ),
        LLMResponse(
            content="Action was vetoed by Tier-1 policy. Escalating to infrastructure team.",
            tool_calls=[],
        ),
    ]

    mock_llm = ScriptedMockLLMClient(script)
    agent = IncidentResponseAgent(llm_client=mock_llm)

    session = agent.run(env, alert)

    assert session.status == SessionStatus.ESCALATED
    assert session.escalation_report is not None
    assert "Tier-1 protected" in session.trace[0].observation["reason"]
