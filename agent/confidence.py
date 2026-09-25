from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class DiagnosticSignal(BaseModel):
    name: str
    weight: float
    detected: bool
    evidence: str


class ConfidenceEvaluator:
    """
    Computes an objective, defensible confidence score for root-cause diagnosis.
    Prevents hallucinated high confidence by gating on verified telemetry convergence.
    """

    @staticmethod
    def calculate_confidence(
        hypothesis: str,
        logs_inspected: bool,
        deployments_inspected: bool,
        metrics_inspected: bool,
        matching_log_errors: int,
        failed_mutations_count: int,
        is_external_dependency: bool = False,
    ) -> float:
        """
        Calculates confidence score between 0.0 and 1.0.

        Scoring Rules:
        - Baseline starting score: 0.20
        - Diagnostic thoroughness: +0.15 for logs, +0.15 for deploys, +0.15 for metrics.
        - Direct evidence bonus: +0.25 if matching stack traces/errors were discovered.
        - External dependency flag: caps local remediation confidence to 0.10 (forces escalation).
        - Penalty: -0.35 for each failed mutation attempt in the session.
        """
        if is_external_dependency:
            # If root cause is third-party/external, confidence to autonomously remediate is near-zero
            return 0.10

        score = 0.20

        if logs_inspected:
            score += 0.15
        if deployments_inspected:
            score += 0.15
        if metrics_inspected:
            score += 0.15

        if matching_log_errors > 0:
            score += 0.25

        # Penalize for each failed attempt to remediate
        score -= (failed_mutations_count * 0.35)

        return max(0.0, min(1.0, round(score, 2)))
