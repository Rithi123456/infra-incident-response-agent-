from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EscalationReport(BaseModel):
    incident_id: str
    target_service: str
    escalation_reason: str
    severity: str
    diagnosed_hypothesis: str
    confidence_score: float
    actions_attempted: List[Dict[str, Any]]
    unresolved_symptoms: List[str]
    recommended_human_action: str
    timestamp: str

    def to_markdown(self) -> str:
        """Renders a clean, formatted handoff memo for an on-call SRE."""
        attempts_md = ""
        if self.actions_attempted:
            for i, act in enumerate(self.actions_attempted, 1):
                attempts_md += f"{i}. **{act.get('action')}** on `{act.get('service')}` - Success: {act.get('success')} (Result: {act.get('message')})\n"
        else:
            attempts_md = "None (autonomous action blocked or deemed unsafe).\n"

        symptoms_md = "\n".join([f"- {s}" for s in self.unresolved_symptoms]) or "- None recorded"

        return f"""### 🚨 Incident Escalation Handoff: {self.incident_id}
**Target Service:** `{self.target_service}` | **Severity:** {self.severity} | **System Confidence:** {self.confidence_score * 100:.1f}%

#### 1. Why Was This Escalated?
> {self.escalation_reason}

#### 2. Root Cause Hypothesis
{self.diagnosed_hypothesis}

#### 3. Actions Attempted by Autonomous Agent
{attempts_md}
#### 4. Active / Unresolved Telemetry Symptoms
{symptoms_md}

#### 5. Recommended Next Steps for Human SRE
👉 {self.recommended_human_action}
"""
