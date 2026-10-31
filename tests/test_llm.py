"""Tests for the Melious client and API key resolution."""
import json
import logging
import subprocess

import httpx2
import pytest

from src.llm import FatalRunError, LLMError, MeliousClient, resolve_api_key

SECRET = "sk-secret-123"
LLM_CONFIG = {
    "base_url": "https://api.melious.test/v1",
    "model": "deepseek-v4.1-flash",
    "timeout_seconds": 5,
    "max_retries": 2,
    "reasoning_effort": None,
    "price_input_per_mtok": 0.20,
    "price_cached_input_per_mtok": 0.01,
    "price_output_per_mtok": 1.00,
}


# --- key resolution -------------------------------------------------------


def _no_keychain(*args, **kwargs):
    return subprocess.CompletedProcess(args, 44, stdout="", stderr="not found")


def test_key_from_environment_skips_other_sources(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MELIOUS_API_KEY=from-file\n")

    def keychain_must_not_run(*args, **kwargs):
        raise AssertionError("Keychain read although env var is set")

    key = resolve_api_key("svc", env_file, environ={"MELIOUS_API_KEY": "from-env"}, run=keychain_must_not_run)

    assert key == "from-env"


def test_key_from_env_file_without_export(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MELIOUS_API_KEY=abc\n")

    assert resolve_api_key("svc", env_file, environ={}, run=_no_keychain) == "abc"


def test_key_from_keychain(tmp_path):
    def keychain(args, **kwargs):
        assert args == ["security", "find-generic-password", "-s", "svc", "-w"]
        assert kwargs["timeout"] == 10
        return subprocess.CompletedProcess(args, 0, stdout="kc-key\n", stderr="")

    assert resolve_api_key("svc", tmp_path / ".env", environ={}, run=keychain) == "kc-key"


def test_hanging_keychain_counts_as_not_found(tmp_path):
    def hangs(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    with pytest.raises(FatalRunError):
        resolve_api_key("svc", tmp_path / ".env", environ={}, run=hangs)


def test_missing_key_error_names_all_sources(tmp_path):
    env_file = tmp_path / ".env"
    with pytest.raises(FatalRunError) as exc:
        resolve_api_key("melious-api-key", env_file, environ={}, run=_no_keychain)

    message = str(exc.value)
    assert "MELIOUS_API_KEY" in message
    assert str(env_file) in message
    assert "melious-api-key" in message


# --- completions ----------------------------------------------------------


def _reply(content: str = '{"ok": true}', finish: str = "stop", extra: dict | None = None) -> dict:
    body = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-v4.1-flash",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": 10_000,
            "completion_tokens": 2_000,
            "total_tokens": 12_000,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 500},
        },
    }
    body.update(extra or {})
    return body


def _client(responses: list, requests: list | None = None, config: dict | None = None) -> MeliousClient:
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(json.loads(request.content))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx2.Response(status, json=body)

    http_client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return MeliousClient(config or LLM_CONFIG, SECRET, http_client=http_client)


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr("openai._base_client.time.sleep", lambda s: None)


MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_complete_returns_content_finish_reason_and_usage():
    completion = _client([(200, _reply())]).complete(MESSAGES, max_tokens=8000)

    assert completion.content == '{"ok": true}'
    assert completion.finish_reason == "stop"
    assert completion.usage.input_tokens == 10_000
    assert completion.usage.output_tokens == 2_000
    assert completion.usage.reasoning_tokens == 500


def test_cost_computed_from_prices_when_not_reported():
    completion = _client([(200, _reply())]).complete(MESSAGES, max_tokens=8000)

    assert completion.usage.cost_eur == pytest.approx(0.0040)


def test_reported_billing_cost_and_provider_are_used():
    extra = {
        "billing_cost": {"credits": "0.0004698"},
        "environment_impact": {"provider_id": "melious", "location": "FI"},
    }
    completion = _client([(200, _reply(extra=extra))]).complete(MESSAGES, max_tokens=8000)

    assert completion.usage.cost_eur == pytest.approx(0.0004698)
    assert completion.usage.provider == "melious"


def test_request_shape_uses_model_json_mode_and_no_reasoning_param_by_default():
    requests: list = []
    _client([(200, _reply())], requests).complete(MESSAGES, max_tokens=8000)

    sent = requests[0]
    assert sent["model"] == "deepseek-v4.1-flash"
    assert sent["max_tokens"] == 8000
    assert sent["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in sent


def test_reasoning_effort_sent_when_configured():
    requests: list = []
    config = LLM_CONFIG | {"reasoning_effort": "none"}
    _client([(200, _reply())], requests, config).complete(MESSAGES, max_tokens=8000)

    assert requests[0]["reasoning_effort"] == "none"


def test_server_error_then_success_is_retried():
    responses = [(503, {"error": {"message": "busy"}}), (200, _reply())]

    completion = _client(responses).complete(MESSAGES, max_tokens=8000)

    assert completion.finish_reason == "stop"


def test_persistent_timeouts_raise_transient_error():
    timeouts = [httpx2.ReadTimeout("slow") for _ in range(3)]

    with pytest.raises(LLMError) as exc:
        _client(timeouts).complete(MESSAGES, max_tokens=8000)

    assert "timed out" in str(exc.value)


@pytest.mark.parametrize("status", [401, 402, 403, 404])
def test_account_level_errors_are_fatal(status):
    body = {"error": {"message": f"problem {status}", "type": "x", "code": "y"}}

    with pytest.raises(FatalRunError) as exc:
        _client([(status, body)]).complete(MESSAGES, max_tokens=8000)

    assert str(status) in str(exc.value)
    assert f"problem {status}" in str(exc.value)


def test_unknown_model_error_names_the_model():
    body = {"error": {"message": "Model not found: deepseek-v4.1-flash", "code": "model_not_found"}}

    with pytest.raises(FatalRunError) as exc:
        _client([(404, body)]).complete(MESSAGES, max_tokens=8000)

    assert "deepseek-v4.1-flash" in str(exc.value)


def test_key_never_appears_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    body = {"error": {"message": "Invalid API key format", "code": "invalid_api_key"}}

    with pytest.raises(FatalRunError) as exc:
        _client([(401, body)]).complete(MESSAGES, max_tokens=8000)

    assert SECRET not in str(exc.value)
    assert SECRET not in caplog.text


def test_unknown_model_error_names_the_model_even_when_body_does_not():
    body = {"error": {"message": "not found", "code": "model_not_found"}}

    with pytest.raises(FatalRunError) as exc:
        _client([(404, body)]).complete(MESSAGES, max_tokens=8000)

    assert LLM_CONFIG["model"] in str(exc.value)
