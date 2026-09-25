from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ServiceStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"


class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ServiceState(BaseModel):
    name: str
    status: ServiceStatus = ServiceStatus.HEALTHY
    cpu_percent: float = 15.0
    memory_mb: float = 250.0
    memory_limit_mb: float = 1024.0
    error_rate_percent: float = 0.05
    p99_latency_ms: float = 45.0
    replica_count: int = 2
    active_version: str = "v1.2.0"
    restart_count: int = 0
    is_protected_tier1: bool = False  # E.g., core database or billing


class LogEntry(BaseModel):
    timestamp: str
    service: str
    level: str  # INFO, WARN, ERROR, CRITICAL
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeploymentRecord(BaseModel):
    service: str
    version: str
    deployed_at: str
    commit_hash: str
    changelog: str
    is_active: bool = False


class AlertEvent(BaseModel):
    alert_id: str
    service: str
    alert_type: str  # e.g., HighErrorRate, MemoryExhaustion, LatencySpike
    severity: AlertSeverity
    trigger_metric: str
    trigger_value: float
    threshold: float
    timestamp: str
    summary: str


class ActionExecutionResult(BaseModel):
    action: str
    service: str
    success: bool
    message: str
    new_status: Optional[ServiceStatus] = None
    execution_time_ms: int = 150
