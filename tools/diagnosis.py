from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from tools.base import Tool
from mock_infra.environment import MockEnvironment


class CheckServiceStatusInput(BaseModel):
    service_name: str = Field(description="Name of the service (e.g., 'web-api', 'auth-service', 'payment-gateway', 'postgres-db', 'redis-cache')")


class CheckServiceStatusTool(Tool):
    name = "check_service_status"
    description = "Inspect the current operational state, status, replica count, active version, and tier classification of a microservice."
    args_schema = CheckServiceStatusInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str) -> Dict[str, Any]:
        return self.env.get_service_status(service_name)


class GetMetricsInput(BaseModel):
    service_name: str = Field(description="Target service name to pull resource utilization telemetry for.")


class GetMetricsTool(Tool):
    name = "get_metrics"
    description = "Retrieve current CPU, memory utilization, error rates (5xx %), and p99 response latencies for a service."
    args_schema = GetMetricsInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str) -> Dict[str, Any]:
        status = self.env.get_service_status(service_name)
        if "error" in status:
            return status
        return {
            "service": service_name,
            "cpu_percent": status["cpu_percent"],
            "memory_mb": status["memory_mb"],
            "memory_limit_mb": status["memory_limit_mb"],
            "memory_usage_percent": round((status["memory_mb"] / status["memory_limit_mb"]) * 100, 2),
            "error_rate_percent": status["error_rate_percent"],
            "p99_latency_ms": status["p99_latency_ms"],
        }


class QueryLogsInput(BaseModel):
    service_name: Optional[str] = Field(default=None, description="Filter logs by service name.")
    level: Optional[str] = Field(default=None, description="Filter logs by severity level: 'INFO', 'WARN', 'ERROR', or 'CRITICAL'.")
    search_query: Optional[str] = Field(default=None, description="Case-insensitive substring search for stack traces or error messages.")
    limit: int = Field(default=10, description="Maximum number of log entries to retrieve.")


class QueryLogsTool(Tool):
    name = "query_logs"
    description = "Query recent application logs and error stack traces across services."
    args_schema = QueryLogsInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(
        self,
        service_name: Optional[str] = None,
        level: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.env.query_logs(
            service_name=service_name,
            level=level,
            search_query=search_query,
            limit=limit,
        )


class GetDeploymentHistoryInput(BaseModel):
    service_name: str = Field(description="Name of service to audit recent releases, versions, and git commit history.")


class GetDeploymentHistoryTool(Tool):
    name = "get_deployment_history"
    description = "Retrieve the chronological deployment log, active release version, and commit changelog for a service."
    args_schema = GetDeploymentHistoryInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str) -> List[Dict[str, Any]]:
        return self.env.get_deployment_history(service_name)
