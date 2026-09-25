from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from tools.base import Tool
from mock_infra.environment import MockEnvironment


class RestartServiceInput(BaseModel):
    service_name: str = Field(description="Name of the service container/pod to restart.")


class RestartServiceTool(Tool):
    name = "restart_service"
    description = "Perform a rolling restart of all pods for a target service. Resets heap memory, clears transient thread locks."
    args_schema = RestartServiceInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str) -> Dict[str, Any]:
        result = self.env.restart_service(service_name)
        return result.model_dump()


class RollbackDeploymentInput(BaseModel):
    service_name: str = Field(description="Name of the service whose deployment should be rolled back.")
    target_version: Optional[str] = Field(default=None, description="Specific previous version to roll back to. Defaults to last stable version.")


class RollbackDeploymentTool(Tool):
    name = "rollback_deployment"
    description = "Roll back a service to its previous stable release version and commit state."
    args_schema = RollbackDeploymentInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str, target_version: Optional[str] = None) -> Dict[str, Any]:
        result = self.env.rollback_deployment(service_name, target_version)
        return result.model_dump()


class ScaleReplicasInput(BaseModel):
    service_name: str = Field(description="Name of the service to scale.")
    target_replicas: int = Field(description="Target number of running container replicas (between 1 and 10).")


class ScaleReplicasTool(Tool):
    name = "scale_replicas"
    description = "Horizontally scale the number of pod replicas for a service to absorb traffic load."
    args_schema = ScaleReplicasInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str, target_replicas: int) -> Dict[str, Any]:
        result = self.env.scale_replicas(service_name, target_replicas)
        return result.model_dump()


class ClearCacheInput(BaseModel):
    service_name: str = Field(description="Service whose cache should be flushed (e.g. 'redis-cache').")
    cache_key_prefix: str = Field(default="all", description="Cache key prefix to invalidate.")


class ClearCacheTool(Tool):
    name = "clear_cache"
    description = "Evict cached keys to purge stale data or corrupted query caches."
    args_schema = ClearCacheInput

    def __init__(self, env: MockEnvironment):
        self.env = env

    def execute(self, service_name: str, cache_key_prefix: str = "all") -> Dict[str, Any]:
        result = self.env.clear_cache(service_name, cache_key_prefix)
        return result.model_dump()
