from abc import ABC, abstractmethod
from typing import Dict, Any, Type
from pydantic import BaseModel


class Tool(ABC):
    """Abstract base class for all agent tools."""

    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Executes the tool logic and returns structured output."""
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        """Converts tool definition to OpenAI/Groq function-calling specification."""
        schema = self.args_schema.model_json_schema()
        # Clean up pydantic schema for OpenAI tool format
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
