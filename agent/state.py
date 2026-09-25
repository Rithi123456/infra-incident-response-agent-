from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from escalation.handoff import EscalationReport


class SessionStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    MAX_STEPS_EXCEEDED = "MAX_STEPS_EXCEEDED"


class StepTrace(BaseModel):
    step_number: int
    thought: Optional[str] = None
    tool_called: Optional[str] = None
    tool_arguments: Dict[str, Any] = Field(default_factory=dict)
    guardrail_decision: Optional[str] = None  # "ALLOWED", "VETOED", or None for read tools
    observation: Any = None
    timestamp: str


class IncidentSessionState(BaseModel):
    alert_id: str
    target_service: str
    status: SessionStatus = SessionStatus.IN_PROGRESS
    step_count: int = 0
    max_steps: int = 8
    
    # Telemetry inspection flags
    logs_inspected: bool = False
    metrics_inspected: bool = False
    deployments_inspected: bool = False
    matching_log_errors: int = 0
    
    # Action and audit tracking
    actions_attempted: List[Dict[str, Any]] = Field(default_factory=list)
    trace: List[StepTrace] = Field(default_factory=list)
    
    # Outcomes
    final_diagnosis: Optional[str] = None
    confidence_score: float = 0.0
    escalation_report: Optional[EscalationReport] = None
