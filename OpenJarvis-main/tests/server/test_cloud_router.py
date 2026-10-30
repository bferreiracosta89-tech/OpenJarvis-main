"""Regression tests for OpenRouter model ID normalization."""

from __future__ import annotations

import pytest

from openjarvis.core.types import Message
from openjarvis.server import cloud_router


def test_get_provider_detects_bare_openrouter_id():
    assert cloud_router.get_provider("anthropic/claude-haiku-4.5") == "openrouter"


def test_get_provider_detects_litellm_prefixed_openrouter_id():
    model = "openrouter/anthropic/claude-haiku-4.5"
    assert cloud_router.get_provider(model) == "openrouter"


def test_cloud_key_status_does_not_expose_values(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")

    status = cloud_router.cloud_key_status()

    assert status["OPENROUTER_API_KEY"] is True
    assert all(isinstance(value, bool) for value in status.values())
    assert "secret" not in str(status)


def test_save_cloud_key_persists_allowlisted_key(monkeypatch, tmp_path):
    key_file = tmp_path / "cloud-keys.env"
    monkeypatch.setattr(cloud_router, "_CLOUD_ENV_FILE", key_file)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    cloud_router.save_cloud_key("OPENAI_API_KEY", "test-key")

    assert key_file.read_text(encoding="utf-8") == "OPENAI_API_KEY=test-key\n"
    assert cloud_router._load_keys()["OPENAI_API_KEY"] == "test-key"


def test_save_cloud_key_rejects_unknown_names(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud_router, "_CLOUD_ENV_FILE", tmp_path / "keys.env")

    with pytest.raises(ValueError, match="Unsupported cloud key"):
        cloud_router.save_cloud_key("EVIL_KEY", "value")


def test_inject_cloud_credentials_loads_persisted_key(monkeypatch, tmp_path):
    cloud_file = tmp_path / "cloud-keys.env"
    cloud_file.write_text("OPENROUTER_API_KEY=persisted-key\n", encoding="utf-8")
    monkeypatch.setattr(cloud_router, "_CLOUD_ENV_FILE", cloud_file)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    cloud_router.inject_cloud_credentials()

    assert cloud_router.os.environ["OPENROUTER_API_KEY"] == "persisted-key"


@pytest.mark.parametrize(
    "requested_model,expected_forwarded_model",
    [
        ("anthropic/claude-haiku-4.5", "anthropic/claude-haiku-4.5"),
        ("openrouter/anthropic/claude-haiku-4.5", "anthropic/claude-haiku-4.5"),
        ("openrouter/auto", "openrouter/auto"),
    ],
)
@pytest.mark.asyncio
async def test_stream_cloud_normalizes_openrouter_model_before_forwarding(
    monkeypatch, requested_model, expected_forwarded_model
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    captured: dict[str, str] = {}

    async def fake_stream_openai(model, messages, temperature, max_tokens, **kwargs):
        captured["model"] = model
        yield "ok"

    monkeypatch.setattr(cloud_router, "_stream_openai", fake_stream_openai)

    tokens = [
        token
        async for token in cloud_router.stream_cloud(
            requested_model, [Message(role="user", content="hi")]
        )
    ]

    assert tokens == ["ok"]
    assert captured["model"] == expected_forwarded_model
