from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from mock_infra.environment import MockEnvironment


class ActionProposal(BaseModel):
    action_name: str
    service_name: str
    arguments: Dict[str, Any] = {}


class PolicyEvaluationResult(BaseModel):
    allowed: bool
    policy_name: str
    reason: str


class GuardrailPolicy(ABC):
    """Abstract class for non-LLM deterministic security and stability policies."""

    @abstractmethod
    def evaluate(
        self,
        proposal: ActionProposal,
        env: MockEnvironment,
        session_action_history: List[ActionProposal],
    ) -> PolicyEvaluationResult:
        pass


class Tier1ProtectionPolicy(GuardrailPolicy):
    """
    Policy: Core Tier-1 infrastructure (databases, auth keyrings) CANNOT
    be autonomously mutated or restarted by the agent without human sign-off.
    """

    def evaluate(
        self,
        proposal: ActionProposal,
        env: MockEnvironment,
        session_action_history: List[ActionProposal],
    ) -> PolicyEvaluationResult:
        svc = env.services.get(proposal.service_name)
        if svc and svc.is_protected_tier1:
            return PolicyEvaluationResult(
                allowed=False,
                policy_name="Tier1ProtectionPolicy",
                reason=(
                    f"VETO: '{proposal.service_name}' is classified as Tier-1 protected infrastructure. "
                    "Autonomous mutations (restarts, rollbacks, scalings) are prohibited. "
                    "Must escalate to human infrastructure lead."
                ),
            )
        return PolicyEvaluationResult(allowed=True, policy_name="Tier1ProtectionPolicy", reason="Service is Tier-2/Tier-3.")


class MaxMutationBudgetPolicy(GuardrailPolicy):
    """
    Policy: Cap autonomous mutation attempts per incident session to prevent runaway cascade failures.
    Default max: 2 mutations.
    """

    def __init__(self, max_mutations: int = 2):
        self.max_mutations = max_mutations

    def evaluate(
        self,
        proposal: ActionProposal,
        env: MockEnvironment,
        session_action_history: List[ActionProposal],
    ) -> PolicyEvaluationResult:
        mutation_count = len(session_action_history)
        if mutation_count >= self.max_mutations:
            return PolicyEvaluationResult(
                allowed=False,
                policy_name="MaxMutationBudgetPolicy",
                reason=(
                    f"VETO: Maximum mutation budget ({self.max_mutations}) exhausted for this incident. "
                    "Autonomous remediation attempts have not recovered health. Immediate human escalation required."
                ),
            )
        return PolicyEvaluationResult(
            allowed=True,
            policy_name="MaxMutationBudgetPolicy",
            reason=f"Current mutations ({mutation_count}) within budget ({self.max_mutations}).",
        )


class AntiThrashingPolicy(GuardrailPolicy):
    """
    Policy: Prevent repeating the exact same failed action repeatedly.
    """

    def evaluate(
        self,
        proposal: ActionProposal,
        env: MockEnvironment,
        session_action_history: List[ActionProposal],
    ) -> PolicyEvaluationResult:
        if not session_action_history:
            return PolicyEvaluationResult(allowed=True, policy_name="AntiThrashingPolicy", reason="First mutation.")

        last_action = session_action_history[-1]
        if (
            last_action.action_name == proposal.action_name
            and last_action.service_name == proposal.service_name
            and last_action.arguments == proposal.arguments
        ):
            return PolicyEvaluationResult(
                allowed=False,
                policy_name="AntiThrashingPolicy",
                reason=(
                    f"VETO: Anti-thrashing triggered. Action '{proposal.action_name}' was just attempted on "
                    f"'{proposal.service_name}' with identical parameters and failed to restore health. "
                    "Try an alternative strategy or escalate."
                ),
            )
        return PolicyEvaluationResult(allowed=True, policy_name="AntiThrashingPolicy", reason="Action is distinct from previous attempt.")
