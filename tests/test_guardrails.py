import pytest
from mock_infra.environment import MockEnvironment
from mock_infra.scenarios import inject_scenario
from guardrails.engine import GuardrailEngine
from guardrails.policies import ActionProposal


def test_tier1_database_veto():
    env = MockEnvironment()
    inject_scenario(env, "INC-004")  # postgres-db deadlock
    engine = GuardrailEngine()

    proposal = ActionProposal(
        action_name="restart_service",
        service_name="postgres-db",
        arguments={},
    )
    result = engine.evaluate_proposal(proposal, env, session_action_history=[])
    assert result.allowed is False
    assert result.policy_name == "Tier1ProtectionPolicy"
    assert "Tier-1 protected" in result.reason


def test_mutation_budget_exhaustion():
    env = MockEnvironment()
    inject_scenario(env, "INC-001")
    engine = GuardrailEngine()

    proposal1 = ActionProposal(action_name="scale_replicas", service_name="web-api", arguments={"target_replicas": 4})
    proposal2 = ActionProposal(action_name="clear_cache", service_name="web-api", arguments={})
    proposal3 = ActionProposal(action_name="restart_service", service_name="web-api", arguments={})

    # First mutation allowed
    assert engine.evaluate_proposal(proposal1, env, []).allowed is True

    # Second mutation allowed
    assert engine.evaluate_proposal(proposal2, env, [proposal1]).allowed is True

    # Third mutation exceeds budget (max 2) -> MUST VETO
    res3 = engine.evaluate_proposal(proposal3, env, [proposal1, proposal2])
    assert res3.allowed is False
    assert res3.policy_name == "MaxMutationBudgetPolicy"


def test_anti_thrashing_veto():
    env = MockEnvironment()
    inject_scenario(env, "INC-002")
    engine = GuardrailEngine()

    proposal = ActionProposal(action_name="restart_service", service_name="web-api", arguments={})

    # First attempt allowed
    assert engine.evaluate_proposal(proposal, env, []).allowed is True

    # Consecutive identical attempt VETOED
    res2 = engine.evaluate_proposal(proposal, env, [proposal])
    assert res2.allowed is False
    assert res2.policy_name == "AntiThrashingPolicy"
