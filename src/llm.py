"""Melious chat-completion client (OpenAI-compatible API) and API key resolution."""
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

ENV_VAR = "MELIOUS_API_KEY"
KEYCHAIN_TIMEOUT_SECONDS = 10
# 401 rejected key, 402 no credit, 403 no access, 404 unknown model: every entry would fail
FATAL_STATUSES = {401, 402, 403, 404}


class FatalRunError(Exception):
    """A problem that would fail every entry; the run must stop."""


class LLMError(Exception):
    """A transient analysis failure; the entry can be retried later."""


@dataclass
class Usage:
    """Token usage and cost of one request."""

    input_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    provider: str | None = None


@dataclass
class Completion:
    """Content and metadata of one chat completion."""

    content: str
    finish_reason: str
    usage: Usage


def resolve_api_key(
    keychain_service: str,
    env_file: Path,
    environ: Mapping[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    """Return the Melious API key from the environment, .env, or the macOS Keychain."""
    environ = os.environ if environ is None else environ
    key = environ.get(ENV_VAR)
    if key:
        return key

    if env_file.exists():
        key = dotenv_values(env_file).get(ENV_VAR)
        if key:
            return key

    try:
        result = run(
            ["security", "find-generic-password", "-s", keychain_service, "-w"],
            capture_output=True,
            text=True,
            timeout=KEYCHAIN_TIMEOUT_SECONDS,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    raise FatalRunError(
        f"No Melious API key found. Set {ENV_VAR} in the environment, add {ENV_VAR}=... to {env_file}, "
        f"or store it in the macOS Keychain under service '{keychain_service}'."
    )


class MeliousClient:
    """Sends JSON-mode chat completions to Melious."""

    def __init__(self, llm_config: dict, api_key: str, http_client=None):
        self._config = llm_config
        self._client = OpenAI(
            api_key=api_key,
            base_url=llm_config["base_url"],
            timeout=llm_config["timeout_seconds"],
            max_retries=llm_config["max_retries"],
            http_client=http_client,
        )

    def complete(self, messages: list[dict], max_tokens: int) -> Completion:
        """Send one request (the SDK retries transient errors) and return the reply."""
        extra_body = {}
        if self._config.get("reasoning_effort"):
            extra_body["reasoning_effort"] = self._config["reasoning_effort"]

        try:
            response = self._client.chat.completions.create(
                model=self._config["model"],
                messages=messages,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body=extra_body or None,
            )
        except APIStatusError as e:
            message = _error_message(e)
            if e.status_code == 404 and self._config["model"] not in message:
                message = f"{message} (model: {self._config['model']})"
            if e.status_code in FATAL_STATUSES:
                raise FatalRunError(f"Melious API rejected the request (HTTP {e.status_code}): {message}") from None
            raise LLMError(f"HTTP {e.status_code}: {message}") from None
        except APITimeoutError:
            raise LLMError(f"request timed out after {self._config['timeout_seconds']}s") from None
        except APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from None

        choice = response.choices[0]
        return Completion(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason or "",
            usage=self._usage(response),
        )

    def _usage(self, response) -> Usage:
        usage = response.usage
        extra = response.model_extra or {}
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cached = 0
        reasoning = 0
        if usage and usage.prompt_tokens_details:
            cached = usage.prompt_tokens_details.cached_tokens or 0
        if usage and usage.completion_tokens_details:
            reasoning = usage.completion_tokens_details.reasoning_tokens or 0

        billed = (extra.get("billing_cost") or {}).get("credits")
        if billed is not None:
            cost = float(billed)
        else:
            cost = (
                (input_tokens - cached) * self._config["price_input_per_mtok"]
                + cached * self._config["price_cached_input_per_mtok"]
                + output_tokens * self._config["price_output_per_mtok"]
            ) / 1_000_000

        return Usage(
            input_tokens=input_tokens,
            cached_tokens=cached,
            reasoning_tokens=reasoning,
            output_tokens=output_tokens,
            cost_eur=cost,
            provider=(extra.get("environment_impact") or {}).get("provider_id"),
        )


def _error_message(error: APIStatusError) -> str:
    """Return the API's error message, cut to a readable length."""
    body = error.body
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])[:300]
    return str(error.message)[:300]
