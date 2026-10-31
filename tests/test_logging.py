"""Tests for CLI logging setup."""
import logging

from src.main import configure_logging


def test_http_client_request_logs_are_quiet():
    names = ("", "httpx", "httpx2", "openai")
    saved = {name: logging.getLogger(name).level for name in names}
    try:
        configure_logging()
        _assert_levels()
    finally:
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


def _assert_levels():
    for name in ("httpx", "httpx2", "openai"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("src.pipeline").getEffectiveLevel() == logging.INFO
