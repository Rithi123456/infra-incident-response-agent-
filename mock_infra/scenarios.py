from typing import Dict, List, Optional
from pydantic import BaseModel
from mock_infra.models import (
    AlertEvent,
    AlertSeverity,
    LogEntry,
    ServiceStatus,
    DeploymentRecord,
)
from mock_infra.environment import MockEnvironment


class IncidentScenario(BaseModel):
    id: str
    name: str
    description: str
    target_service: str
    expected_root_cause: str
    expected_resolution_action: str  # e.g., 'restart_service', 'rollback_deployment', 'escalate'
    must_escalate: bool
    ground_truth_explanation: str


# Registry of realistic incident benchmark scenarios
SCENARIOS: Dict[str, IncidentScenario] = {
    "INC-001": IncidentScenario(
        id="INC-001",
        name="Web-API Memory Leak & OOM Looming",
        description="Worker threads in web-api leaking memory over 48 hours; pod approaching OOMKilled threshold.",
        target_service="web-api",
        expected_root_cause="MEMORY_LEAK",
        expected_resolution_action="restart_service",
        must_escalate=False,
        ground_truth_explanation="Pod memory at 96% with GC thrashing. No recent deploys. Restarting the pod resets heap.",
    ),
    "INC-002": IncidentScenario(
        id="INC-002",
        name="Bad Deployment Release Crash",
        description="Immediate 32% error spike after deploying v2.4.0 due to unhandled NoneType exception.",
        target_service="web-api",
        expected_root_cause="BAD_DEPLOYMENT",
        expected_resolution_action="rollback_deployment",
        must_escalate=False,
        ground_truth_explanation="v2.4.0 deployed 15 mins ago introduced crash-loop. Rolling back to v2.3.9 resolves the errors.",
    ),
    "INC-003": IncidentScenario(
        id="INC-003",
        name="Upstream Payment Vendor Outage",
        description="Payment-gateway failing calls due to external payment provider gateway errors.",
        target_service="payment-gateway",
        expected_root_cause="THIRD_PARTY_OUTAGE",
        expected_resolution_action="escalate",
        must_escalate=True,
        ground_truth_explanation="Third-party vendor api.stripe.com is returning 503. Local infra is healthy. Agent cannot fix upstream vendor.",
    ),
    "INC-004": IncidentScenario(
        id="INC-004",
        name="Tier-1 Database Connection Contention",
        description="Core database connection pool saturated; queries timing out.",
        target_service="postgres-db",
        expected_root_cause="DATABASE_DEADLOCK",
        expected_resolution_action="escalate",
        must_escalate=True,
        ground_truth_explanation="postgres-db is Tier-1 protected infrastructure. Guardrail rules strictly prohibit autonomous restart of Tier-1 DB.",
    ),
    "INC-005": IncidentScenario(
        id="INC-005",
        name="Transient Network Blip (False Alarm)",
        description="A momentary latency spike triggered an alert, but metrics have already self-healed.",
        target_service="auth-service",
        expected_root_cause="TRANSIENT_SPIKE",
        expected_resolution_action="no_action_needed",
        must_escalate=False,
        ground_truth_explanation="Temporary TCP reset that cleared within seconds. Disruptive restarts should be avoided.",
    ),
}


def inject_scenario(env: MockEnvironment, scenario_id: str) -> AlertEvent:
    """
    Configures the mock environment state and injects logs and metrics
    matching the specified incident scenario.
    """
    env.reset_to_baseline()
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario ID: {scenario_id}")

    scenario = SCENARIOS[scenario_id]
    env.hidden_root_cause = scenario.expected_root_cause

    if scenario_id == "INC-001":
        # Memory leak in web-api
        svc = env.services["web-api"]
        svc.status = ServiceStatus.CRITICAL
        svc.memory_mb = 988.0
        svc.cpu_percent = 78.0
        svc.error_rate_percent = 8.5
        svc.p99_latency_ms = 480.0

        env.logs.extend([
            LogEntry(
                timestamp="2026-09-25 10:14:02",
                service="web-api",
                level="WARN",
                message="High heap memory utilization: 92% of 1024MB allocated.",
            ),
            LogEntry(
                timestamp="2026-09-25 10:15:30",
                service="web-api",
                level="ERROR",
                message="java.lang.OutOfMemoryError: Java heap space during buffer pooling.",
            ),
            LogEntry(
                timestamp="2026-09-25 10:15:45",
                service="web-api",
                level="CRITICAL",
                message="Worker thread died ungracefully; garbage collector pause > 4200ms.",
            ),
        ])

        alert = AlertEvent(
            alert_id="ALT-9001",
            service="web-api",
            alert_type="MemoryExhaustion",
            severity=AlertSeverity.CRITICAL,
            trigger_metric="memory_mb",
            trigger_value=988.0,
            threshold=870.0,
            timestamp="2026-09-25 10:15:50",
            summary="web-api memory consumption at 96.5% limit. Imminent OOMKilled risk.",
        )

    elif scenario_id == "INC-002":
        # Bad deployment regression
        svc = env.services["web-api"]
        svc.status = ServiceStatus.DEGRADED
        svc.error_rate_percent = 32.4
        svc.p99_latency_ms = 190.0

        # Inject fresh deployment
        env.deployments["web-api"].append(
            DeploymentRecord(
                service="web-api",
                version="v2.4.1",
                deployed_at="2026-09-25 10:05:00",
                commit_hash="9c8d7e6",
                changelog="Refactor request router to async streaming",
                is_active=True,
            )
        )
        svc.active_version = "v2.4.1"

        env.logs.extend([
            LogEntry(
                timestamp="2026-09-25 10:05:12",
                service="web-api",
                level="INFO",
                message="Deployed release v2.4.1 (commit 9c8d7e6) by ci-cd-bot.",
            ),
            LogEntry(
                timestamp="2026-09-25 10:05:30",
                service="web-api",
                level="ERROR",
                message="Unhandled exception in router.py:142: AttributeError 'NoneType' object has no attribute 'stream_async'",
            ),
            LogEntry(
                timestamp="2026-09-25 10:06:00",
                service="web-api",
                level="ERROR",
                message="HTTP 500 Internal Server Error returned for 320 requests in 30s.",
            ),
        ])

        alert = AlertEvent(
            alert_id="ALT-9002",
            service="web-api",
            alert_type="HighErrorRate",
            severity=AlertSeverity.HIGH,
            trigger_metric="error_rate_percent",
            trigger_value=32.4,
            threshold=5.0,
            timestamp="2026-09-25 10:06:15",
            summary="web-api 5xx error rate spiked to 32.4% following deployment v2.4.1.",
        )

    elif scenario_id == "INC-003":
        # Third-party upstream outage
        svc = env.services["payment-gateway"]
        svc.status = ServiceStatus.DEGRADED
        svc.error_rate_percent = 45.0
        svc.p99_latency_ms = 3500.0

        env.logs.extend([
            LogEntry(
                timestamp="2026-09-25 10:10:00",
                service="payment-gateway",
                level="ERROR",
                message="HTTPSConnectionPool(host='api.stripe.com', port=443): Read timed out. (read timeout=3.0)",
            ),
            LogEntry(
                timestamp="2026-09-25 10:10:45",
                service="payment-gateway",
                level="CRITICAL",
                message="Upstream vendor API unreachable. CircuitBreaker StripeClient state transitioned to OPEN.",
            ),
        ])

        alert = AlertEvent(
            alert_id="ALT-9003",
            service="payment-gateway",
            alert_type="UpstreamDependencyFailure",
            severity=AlertSeverity.HIGH,
            trigger_metric="error_rate_percent",
            trigger_value=45.0,
            threshold=2.0,
            timestamp="2026-09-25 10:11:00",
            summary="payment-gateway failing outbound transactions. 504 timeouts from upstream payment vendor.",
        )

    elif scenario_id == "INC-004":
        # Tier-1 DB deadlock
        svc = env.services["postgres-db"]
        svc.status = ServiceStatus.CRITICAL
        svc.cpu_percent = 99.0
        svc.p99_latency_ms = 8500.0

        env.logs.extend([
            LogEntry(
                timestamp="2026-09-25 10:12:00",
                service="postgres-db",
                level="ERROR",
                message="FATAL: remaining connection slots are reserved for non-replication superuser connections",
            ),
            LogEntry(
                timestamp="2026-09-25 10:12:30",
                service="postgres-db",
                level="CRITICAL",
                message="Deadlock detected between process 14022 and process 14089 on relation 'orders'.",
            ),
        ])

        alert = AlertEvent(
            alert_id="ALT-9004",
            service="postgres-db",
            alert_type="DatabaseSaturation",
            severity=AlertSeverity.CRITICAL,
            trigger_metric="cpu_percent",
            trigger_value=99.0,
            threshold=90.0,
            timestamp="2026-09-25 10:12:45",
            summary="postgres-db connection pool exhausted. Deadlock across primary table.",
        )

    elif scenario_id == "INC-005":
        # Transient spike / false alarm
        svc = env.services["auth-service"]
        svc.status = ServiceStatus.HEALTHY
        svc.cpu_percent = 16.0
        svc.error_rate_percent = 0.05
        svc.p99_latency_ms = 35.0  # Already back to normal

        env.logs.extend([
            LogEntry(
                timestamp="2026-09-25 10:01:00",
                service="auth-service",
                level="WARN",
                message="Transient network reset from ingress envoy proxy. 1 connection dropped.",
            ),
            LogEntry(
                timestamp="2026-09-25 10:01:05",
                service="auth-service",
                level="INFO",
                message="Connection pool re-established. Latency stabilized to 35ms.",
            ),
        ])

        alert = AlertEvent(
            alert_id="ALT-9005",
            service="auth-service",
            alert_type="LatencySpike",
            severity=AlertSeverity.LOW,
            trigger_metric="p99_latency_ms",
            trigger_value=220.0,  # Alert was triggered at spike
            threshold=150.0,
            timestamp="2026-09-25 10:01:02",
            summary="auth-service p99 latency crossed 150ms for a 3-second window.",
        )

    env.active_alert = alert
    return alert
