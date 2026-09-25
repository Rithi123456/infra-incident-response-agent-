from typing import List, Dict, Any, Optional
from mock_infra.environment import MockEnvironment
from guardrails.policies import (
    GuardrailPolicy,
    ActionProposal,
    PolicyEvaluationResult,
    Tier1ProtectionPolicy,
    MaxMutationBudgetPolicy,
    AntiThrashingPolicy,
)


class GuardrailEngine:
    """
    Deterministic rule engine that validates every proposed remediation action
    prior to execution. LLMs are NOT allowed to bypass or self-approve.
    """

    def __init__(self, policies: Optional[List[GuardrailPolicy]] = None):
        if policies is None:
            self.policies = [
                Tier1ProtectionPolicy(),
                MaxMutationBudgetPolicy(max_mutations=2),
                AntiThrashingPolicy(),
            ]
        else:
            self.policies = policies

        self.audit_log: List[Dict[str, Any]] = []

    def evaluate_proposal(
        self,
        proposal: ActionProposal,
        env: MockEnvironment,
        session_action_history: List[ActionProposal],
    ) -> PolicyEvaluationResult:
        """
        Runs the proposal through all deterministic safety policies.
        Rejection is fast-fail: first policy violation halts execution.
        """
        for policy in self.policies:
            eval_result = policy.evaluate(proposal, env, session_action_history)
            if not eval_result.allowed:
                self.audit_log.append({
                    "action": proposal.action_name,
                    "service": proposal.service_name,
                    "arguments": proposal.arguments,
                    "decision": "VETOED",
                    "policy": eval_result.policy_name,
                    "reason": eval_result.reason,
                })
                return eval_result

        # All policies cleared
        self.audit_log.append({
            "action": proposal.action_name,
            "service": proposal.service_name,
            "arguments": proposal.arguments,
            "decision": "ALLOWED",
            "policy": "ALL_PASSED",
            "reason": "All safety policies passed.",
        })
        return PolicyEvaluationResult(
            allowed=True,
            policy_name="ALL_PASSED",
            reason="Action conforms to all safety and blast-radius constraints.",
        )
