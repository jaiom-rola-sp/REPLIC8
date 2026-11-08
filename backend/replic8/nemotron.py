"""Client for Nemotron through NVIDIA's OpenAI-compatible chat API.

The model name and key are not decided yet (PRD section 10), so both come from
environment variables and nothing is guessed:

- NVIDIA_API_KEY            required, never logged or put in error messages
- REPLIC8_NEMOTRON_MODEL    required, e.g. the model id shown on build.nvidia.com
- REPLIC8_NEMOTRON_BASE_URL optional, defaults to https://integrate.api.nvidia.com/v1
- REPLIC8_NEMOTRON_STRUCTURED optional, default "1": send the JSON schema as
  `response_format` (json_schema). NVIDIA's API rejects `nvext.guided_json` (tested
  2026-11-07). Output is validated by guard.py either way.
- REPLIC8_NEMOTRON_THINKING optional, default "0": reasoning mode. Off by default
  because in testing it used ~3,700 tokens and cut the answer off.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("replic8.nemotron")
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
MAX_RESPONSE_BYTES = 2_000_000
RETRY_STATUS = {429, 500, 502, 503, 504}

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
FENCE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.S)


class ModelError(Exception):
    """Safe to show: never contains the API key, the prompt, or the raw response."""


@dataclass(frozen=True)
class ModelConfig:
    api_key: str
    model: str
    base_url: str = DEFAULT_BASE_URL
    structured: bool = True
    thinking: bool = False
    timeout_s: float = 120.0
    max_tokens: int = 4096
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "ModelConfig":
        key = os.environ.get("NVIDIA_API_KEY", "").strip()
        model = os.environ.get("REPLIC8_NEMOTRON_MODEL", "").strip()
        if not key:
            raise ModelError("NVIDIA_API_KEY is not set")
        if not model:
            raise ModelError("REPLIC8_NEMOTRON_MODEL is not set")
        config = cls(
            api_key=key,
            model=model,
            base_url=os.environ.get("REPLIC8_NEMOTRON_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            structured=os.environ.get("REPLIC8_NEMOTRON_STRUCTURED", "1") == "1",
            thinking=os.environ.get("REPLIC8_NEMOTRON_THINKING", "0") == "1",
        )
        config.validate()
        return config

    def validate(self) -> None:
        parts = urlsplit(self.base_url)
        # https only, so the key is never sent in clear text.
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ModelError("model base URL must be a plain https URL")

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return f"ModelConfig(model={self.model!r}, base_url={self.base_url!r})"


def extract_json_text(content: str) -> str:
    """Drop reasoning blocks and a surrounding code fence. Validation happens in guard.py."""
    text = THINK_BLOCK.sub("", content).strip()
    match = FENCE.match(text)
    return match.group(1).strip() if match else text


class NemotronClient:
    def __init__(self, config: ModelConfig, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        config.validate()
        self.config = config
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_s,
            transport=transport,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {config.api_key}", "Accept": "application/json"},
        )

    def complete_json(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        """Ask for a JSON answer and return the JSON text (not yet trusted)."""
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": self.config.max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": self.config.thinking},
        }
        if schema is not None and self.config.structured:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}

        last = "no attempt made"
        for attempt in range(self.config.max_retries + 1):
            if attempt:
                self._sleep(min(2 ** attempt, 20))
            try:
                resp = self._http.post("/chat/completions", json=body)
            except httpx.TimeoutException:
                last = "model request timed out"
                continue
            except httpx.HTTPError as exc:
                last = f"model request failed ({type(exc).__name__})"
                continue
            if resp.status_code in RETRY_STATUS:
                last = f"model API returned {resp.status_code}"
                continue
            if resp.status_code in (401, 403):
                raise ModelError("model API rejected the key (check NVIDIA_API_KEY)")
            if resp.status_code != 200:
                raise ModelError(f"model API returned {resp.status_code}")
            if len(resp.content) > MAX_RESPONSE_BYTES:
                raise ModelError("model response too large")
            try:
                choice = resp.json()["choices"][0]
                content = choice["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ModelError("model response had an unexpected shape") from exc
            if choice.get("finish_reason") == "length":
                raise ModelError("model answer was cut off (max_tokens reached)")
            if not isinstance(content, str) or not content.strip():
                raise ModelError("model returned an empty answer")
            usage = resp.json().get("usage") or {}
            log.info("model call ok model=%s tokens=%s", self.config.model, usage.get("total_tokens"))
            return extract_json_text(content)
        raise ModelError(f"{last} after {self.config.max_retries + 1} attempts")

    def close(self) -> None:
        self._http.close()
