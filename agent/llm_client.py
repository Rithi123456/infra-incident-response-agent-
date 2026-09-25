import os
import time
import json
import random
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class LLMResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    raw_response: Optional[Any] = None


class ResilientLLMClient:
    """
    Unified LLM client supporting Groq, OpenAI, and a Mock provider.
    Includes built-in rate-limiting, token-bucket pacing, and exponential backoff
    to guarantee free-tier runs won't crash on 429 rate limit errors.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_rpm: int = 25,
    ):
        self.provider = provider or os.getenv("LLM_PROVIDER", "groq").lower()
        self.model = model or os.getenv("GROQ_MODEL" if self.provider == "groq" else "OPENAI_MODEL", "")
        self.max_rpm = int(os.getenv("MAX_CALLS_PER_MINUTE", str(max_rpm)))
        self.min_interval = 60.0 / self.max_rpm if self.max_rpm > 0 else 0.0
        self.last_call_time = 0.0

        # Initialize provider client
        if self.provider == "groq":
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                print("WARNING: GROQ_API_KEY not found in environment.")
            self.client = Groq(api_key=api_key)
            if not self.model:
                self.model = "openai/gpt-oss-120b"

        elif self.provider == "openai":
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("WARNING: OPENAI_API_KEY not found in environment.")
            self.client = OpenAI(api_key=api_key)
            if not self.model:
                self.model = "gpt-4o-mini"
        elif self.provider == "mock":
            self.client = None
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def _pace_request(self):
        """Paces requests to stay safely under provider RPM quota."""
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        self.last_call_time = time.time()

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_retries: int = 5,
    ) -> LLMResponse:
        """
        Executes a chat completion with function calling tools, wrapped
        in exponential backoff to handle transient network issues or 429 rate limits.
        """
        if self.provider == "mock":
            # For offline testing
            return LLMResponse(content="Mock response: no action taken.")

        backoff = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                self._pace_request()

                params = {
                    "model": self.model,
                    "messages": messages,
                }
                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = "auto"

                response = self.client.chat.completions.create(**params)
                message = response.choices[0].message

                # Parse tool calls if returned
                parsed_tool_calls: List[ToolCall] = []
                if message.tool_calls:
                    for tc in message.tool_calls:
                        parsed_tool_calls.append(
                            ToolCall(
                                id=tc.id,
                                name=tc.function.name,
                                arguments=json.loads(tc.function.arguments),
                            )
                        )

                return LLMResponse(
                    content=message.content,
                    tool_calls=parsed_tool_calls,
                    raw_response=response,
                )

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate limit" in err_str
                if attempt == max_retries:
                    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {e}")

                sleep_duration = backoff + random.uniform(0.5, 1.5)
                if is_rate_limit:
                    sleep_duration += 5.0  # Extra backoff for 429 rate limits
                    print(f"[RateLimit 429] Backing off for {sleep_duration:.1f}s (Attempt {attempt}/{max_retries})...")
                else:
                    print(f"[Transient Error] Retrying in {sleep_duration:.1f}s ({e})...")

                time.sleep(sleep_duration)
                backoff *= 2
