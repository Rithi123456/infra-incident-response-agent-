import copy
from datetime import datetime
from typing import Dict, List, Optional, Any
from mock_infra.models import (
    ServiceState,
    ServiceStatus,
    LogEntry,
    DeploymentRecord,
    AlertEvent,
    ActionExecutionResult,
)


class MockEnvironment:
    """
    In-memory state machine simulating cloud microservices, metrics,
    logs, deployment histories, and mutation operations.
    """

    def __init__(self):
        self.services: Dict[str, ServiceState] = {}
        self.logs: List[LogEntry] = []
        self.deployments: Dict[str, List[DeploymentRecord]] = {}
        self.active_alert: Optional[AlertEvent] = None
        self.hidden_root_cause: Optional[str] = None
        self.action_history: List[ActionExecutionResult] = []

    def reset_to_baseline(self):
        """Initializes a normal, healthy microservices cluster."""
        self.services = {
            "web-api": ServiceState(
                name="web-api",
                status=ServiceStatus.HEALTHY,
                cpu_percent=25.0,
                memory_mb=350.0,
                memory_limit_mb=1024.0,
                error_rate_percent=0.08,
                p99_latency_ms=65.0,
                replica_count=3,
                active_version="v2.4.0",
                is_protected_tier1=False,
            ),
            "auth-service": ServiceState(
                name="auth-service",
                status=ServiceStatus.HEALTHY,
                cpu_percent=18.0,
                memory_mb=210.0,
                memory_limit_mb=512.0,
                error_rate_percent=0.01,
                p99_latency_ms=25.0,
                replica_count=2,
                active_version="v1.8.2",
                is_protected_tier1=False,
            ),
            "payment-gateway": ServiceState(
                name="payment-gateway",
                status=ServiceStatus.HEALTHY,
                cpu_percent=12.0,
                memory_mb=190.0,
                memory_limit_mb=512.0,
                error_rate_percent=0.02,
                p99_latency_ms=110.0,
                replica_count=2,
                active_version="v3.1.0",
                is_protected_tier1=False,
            ),
            "postgres-db": ServiceState(
                name="postgres-db",
                status=ServiceStatus.HEALTHY,
                cpu_percent=30.0,
                memory_mb=1200.0,
                memory_limit_mb=4096.0,
                error_rate_percent=0.0,
                p99_latency_ms=15.0,
                replica_count=1,
                active_version="v15.4",
                is_protected_tier1=True,  # Critical Tier-1 database
            ),
            "redis-cache": ServiceState(
                name="redis-cache",
                status=ServiceStatus.HEALTHY,
                cpu_percent=8.0,
                memory_mb=450.0,
                memory_limit_mb=2048.0,
                error_rate_percent=0.0,
                p99_latency_ms=2.0,
                replica_count=1,
                active_version="v7.2",
                is_protected_tier1=False,
            ),
        }

        self.deployments = {
            "web-api": [
                DeploymentRecord(
                    service="web-api",
                    version="v2.3.9",
                    deployed_at="2026-09-24 10:00:00",
                    commit_hash="7a8b9c0",
                    changelog="Bugfix: sanitize input in search headers",
                    is_active=False,
                ),
                DeploymentRecord(
                    service="web-api",
                    version="v2.4.0",
                    deployed_at="2026-09-25 09:30:00",
                    commit_hash="1f2e3d4",
                    changelog="Feature: enable asynchronous request streaming",
                    is_active=True,
                ),
            ],
            "payment-gateway": [
                DeploymentRecord(
                    service="payment-gateway",
                    version="v3.1.0",
                    deployed_at="2026-09-20 14:00:00",
                    commit_hash="4b5c6d7",
                    changelog="Bump stripe-client to 9.2",
                    is_active=True,
                )
            ],
        }

        self.logs = [
            LogEntry(
                timestamp="2026-09-25 10:00:00",
                service="web-api",
                level="INFO",
                message="Server listening on port 8080. Health check passed.",
            ),
            LogEntry(
                timestamp="2026-09-25 10:00:05",
                service="auth-service",
                level="INFO",
                message="JWKS key rotation completed successfully.",
            ),
        ]
        self.active_alert = None
        self.hidden_root_cause = None
        self.action_history = []

    # -------------------------------------------------------------
    # Observability & Diagnosis Read APIs (Used by Agent Tools)
    # -------------------------------------------------------------

    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Returns the current state and status of a specific service."""
        if service_name not in self.services:
            return {"error": f"Service '{service_name}' not found."}
        svc = self.services[service_name]
        return svc.model_dump()

    def get_all_services_overview(self) -> Dict[str, Any]:
        """Returns high-level status of all services."""
        return {
            name: {
                "status": svc.status,
                "cpu_percent": svc.cpu_percent,
                "memory_mb": svc.memory_mb,
                "memory_limit_mb": svc.memory_limit_mb,
                "error_rate_percent": svc.error_rate_percent,
                "p99_latency_ms": svc.p99_latency_ms,
                "active_version": svc.active_version,
            }
            for name, svc in self.services.items()
        }

    def query_logs(
        self,
        service_name: Optional[str] = None,
        level: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Queries the simulated log stream with optional filters."""
        results = []
        for entry in reversed(self.logs):
            if service_name and entry.service != service_name:
                continue
            if level and entry.level.upper() != level.upper():
                continue
            if search_query and search_query.lower() not in entry.message.lower():
                continue
            results.append(entry.model_dump())
            if len(results) >= limit:
                break
        return list(reversed(results))

    def get_deployment_history(self, service_name: str) -> List[Dict[str, Any]]:
        """Returns recent deployments and git commit logs for a service."""
        if service_name not in self.deployments:
            return []
        return [d.model_dump() for d in self.deployments[service_name]]

    # -------------------------------------------------------------
    # Remediation Action Mutation APIs (Called by Action Tools)
    # -------------------------------------------------------------

    def restart_service(self, service_name: str) -> ActionExecutionResult:
        """Simulates restarting container/pods for a given service."""
        if service_name not in self.services:
            res = ActionExecutionResult(
                action="restart_service",
                service=service_name,
                success=False,
                message=f"Service '{service_name}' does not exist.",
            )
            self.action_history.append(res)
            return res

        svc = self.services[service_name]
        svc.restart_count += 1

        # Check if the root cause was solved by restart
        if self.hidden_root_cause == "MEMORY_LEAK":
            # Restart purges leaked memory buffer
            svc.memory_mb = 280.0
            svc.status = ServiceStatus.HEALTHY
            svc.error_rate_percent = 0.05
            svc.p99_latency_ms = 50.0
            msg = f"Service '{service_name}' restarted. Memory footprint reset from leak to 280MB. Pod healthy."
            success = True
        elif self.hidden_root_cause == "BAD_DEPLOYMENT":
            # Restarting a bad deployment does NOT fix buggy code!
            msg = f"Service '{service_name}' restarted, but crash-loop continues because faulty binary is still active."
            success = False
        elif self.hidden_root_cause == "THIRD_PARTY_OUTAGE":
            # Restarting local service does NOT fix external vendor
            msg = f"Service '{service_name}' restarted, but downstream upstream vendor still returning 503 Gateway Errors."
            success = False
        else:
            # Baseline restart behavior
            svc.status = ServiceStatus.HEALTHY
            msg = f"Service '{service_name}' restarted successfully."
            success = True

        res = ActionExecutionResult(
            action="restart_service",
            service=service_name,
            success=success,
            message=msg,
            new_status=svc.status,
        )
        self.action_history.append(res)
        return res

    def rollback_deployment(self, service_name: str, target_version: Optional[str] = None) -> ActionExecutionResult:
        """Simulates rolling back to a previous deployment."""
        if service_name not in self.services:
            res = ActionExecutionResult(
                action="rollback_deployment",
                service=service_name,
                success=False,
                message=f"Service '{service_name}' does not exist.",
            )
            self.action_history.append(res)
            return res

        history = self.deployments.get(service_name, [])
        if len(history) < 2 and not target_version:
            res = ActionExecutionResult(
                action="rollback_deployment",
                service=service_name,
                success=False,
                message=f"Cannot rollback '{service_name}': no previous version recorded.",
            )
            self.action_history.append(res)
            return res

        # Determine target version
        if not target_version:
            target_version = history[-2].version

        svc = self.services[service_name]
        previous_version = svc.active_version
        svc.active_version = target_version

        # Update deployment flags
        for d in history:
            d.is_active = (d.version == target_version)

        # Effect on incident
        if self.hidden_root_cause == "BAD_DEPLOYMENT":
            svc.status = ServiceStatus.HEALTHY
            svc.error_rate_percent = 0.02
            svc.p99_latency_ms = 45.0
            msg = f"Successfully rolled back '{service_name}' from {previous_version} to {target_version}. Error rates normalized."
            success = True
        else:
            msg = f"Rolled back '{service_name}' to {target_version}, but root issue was not deployment-related. Status remains {svc.status}."
            success = False

        res = ActionExecutionResult(
            action="rollback_deployment",
            service=service_name,
            success=success,
            message=msg,
            new_status=svc.status,
        )
        self.action_history.append(res)
        return res

    def scale_replicas(self, service_name: str, target_replicas: int) -> ActionExecutionResult:
        """Scales replica count up or down."""
        if service_name not in self.services:
            res = ActionExecutionResult(
                action="scale_replicas",
                service=service_name,
                success=False,
                message=f"Service '{service_name}' does not exist.",
            )
            self.action_history.append(res)
            return res

        svc = self.services[service_name]
        old_count = svc.replica_count
        svc.replica_count = target_replicas

        if self.hidden_root_cause == "TRAFFIC_SPIKE":
            svc.status = ServiceStatus.HEALTHY
            svc.cpu_percent = 35.0
            svc.p99_latency_ms = 60.0
            msg = f"Scaled '{service_name}' from {old_count} to {target_replicas} replicas. Latency and CPU normalized."
            success = True
        else:
            msg = f"Scaled '{service_name}' from {old_count} to {target_replicas} replicas. Underlying problem persists."
            success = False

        res = ActionExecutionResult(
            action="scale_replicas",
            service=service_name,
            success=success,
            message=msg,
            new_status=svc.status,
        )
        self.action_history.append(res)
        return res

    def clear_cache(self, service_name: str, cache_key_prefix: str = "all") -> ActionExecutionResult:
        """Clears memory/redis cache entries."""
        res = ActionExecutionResult(
            action="clear_cache",
            service=service_name,
            success=True,
            message=f"Cache cleared for '{service_name}' (prefix: '{cache_key_prefix}').",
        )
        self.action_history.append(res)
        return res

    def is_service_recovered(self, service_name: str) -> bool:
        """Determines if the service is currently within acceptable health thresholds."""
        if service_name not in self.services:
            return False
        svc = self.services[service_name]
        return (
            svc.status == ServiceStatus.HEALTHY
            and svc.error_rate_percent <= 1.0
            and svc.memory_mb < (svc.memory_limit_mb * 0.85)
            and svc.p99_latency_ms <= 150.0
        )
