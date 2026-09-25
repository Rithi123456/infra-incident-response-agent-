import pytest
from mock_infra.environment import MockEnvironment
from mock_infra.scenarios import inject_scenario
from agent.simulated_client import ScriptedScenarioLLMClient
from agent.graph import LangGraphIncidentAgent
from agent.state import SessionStatus


def test_langgraph_mermaid_export():
    client = ScriptedScenarioLLMClient("INC-001")
    agent = LangGraphIncidentAgent(llm_client=client)
    mermaid = agent.get_mermaid_graph()
    assert "diagnose_and_decide" in mermaid
    assert "guardrail_gate" in mermaid
    assert "execute_remediation" in mermaid


def test_langgraph_memory_leak_resolved():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-001")

    client = ScriptedScenarioLLMClient("INC-001")
    agent = LangGraphIncidentAgent(llm_client=client)

    session = agent.run(env, alert)

    assert session.status == SessionStatus.RESOLVED
    assert env.is_service_recovered("web-api") is True
    assert len(session.actions_attempted) == 1
    assert session.actions_attempted[0]["action"] == "restart_service"


def test_langgraph_tier1_guardrail_escalated():
    env = MockEnvironment()
    alert = inject_scenario(env, "INC-004")

    client = ScriptedScenarioLLMClient("INC-004")
    agent = LangGraphIncidentAgent(llm_client=client)

    session = agent.run(env, alert)

    assert session.status == SessionStatus.ESCALATED
    assert session.escalation_report is not None
