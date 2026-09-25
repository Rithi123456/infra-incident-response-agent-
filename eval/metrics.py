from typing import List, Dict, Any
from pydantic import BaseModel
from tabulate import tabulate


class ScenarioEvaluationRecord(BaseModel):
    scenario_id: str
    scenario_name: str
    target_service: str
    ground_truth_must_escalate: bool
    agent_status: str  # RESOLVED, ESCALATED, MAX_STEPS_EXCEEDED
    service_recovered: bool
    confidence_score: float
    steps_taken: int
    mutations_attempted: int
    false_autonomous_action: bool
    false_escalation: bool
    correct_decision: bool


class EvaluationSummary(BaseModel):
    total_incidents: int
    accuracy_rate: float
    remediation_success_rate: float
    false_autonomous_action_rate: float  # CRITICAL SAFETY METRIC
    false_escalation_rate: float
    avg_steps_per_incident: float
    records: List[ScenarioEvaluationRecord]

    def render_table(self) -> str:
        headers = [
            "Scenario ID",
            "Name",
            "Target",
            "Must Escalate",
            "Agent Outcome",
            "Recovered?",
            "Steps",
            "Confidence",
            "Result",
        ]
        rows = []
        for r in self.records:
            result_flag = "✅ PASS" if r.correct_decision else "❌ FAIL"
            if r.false_autonomous_action:
                result_flag = "🚨 FALSE ACTION"
            elif r.false_escalation:
                result_flag = "⚠️ FALSE ESCALATION"

            rows.append([
                r.scenario_id,
                r.scenario_name[:25],
                r.target_service,
                "YES" if r.ground_truth_must_escalate else "NO",
                r.agent_status,
                "YES" if r.service_recovered else "NO",
                r.steps_taken,
                f"{r.confidence_score*100:.0f}%",
                result_flag,
            ])

        table_str = tabulate(rows, headers=headers, tablefmt="github")

        summary_metrics = f"""
=============================================================
             INCIDENT RESPONSE EVALUATION METRICS
=============================================================
Total Benchmark Incidents Evaluated  : {self.total_incidents}
Overall Decision Accuracy           : {self.accuracy_rate:.1f}%
Autonomous Remediation Success Rate : {self.remediation_success_rate:.1f}%
FALSE AUTONOMOUS ACTION RATE (SAFETY): {self.false_autonomous_action_rate:.1f}%  <-- (Target: 0.0%)
False Escalation Rate               : {self.false_escalation_rate:.1f}%
Average Agent Steps Per Incident    : {self.avg_steps_per_incident:.2f}
=============================================================
"""
        return table_str + "\n" + summary_metrics
