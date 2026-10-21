from types import SimpleNamespace

import pytest

from auditauthor.adapters.llm import LiteLLMClient
from auditauthor.config import Settings
from auditauthor.domain.models import Extraction


def test_invalid_json_bounded_retries(monkeypatch):
    import litellm

    calls = []

    def bad(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="not json"))
            ]
        )

    monkeypatch.setattr(litellm, "completion", bad)
    monkeypatch.setattr("auditauthor.adapters.llm.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="structured"):
        LiteLLMClient(Settings(model_attempts=2)).generate(
            "system", "source", Extraction, "openai/test"
        )
    assert len(calls) == 2
    assert calls[0]["response_format"]["json_schema"]["strict"]


def test_timeout_retries_and_redacted_errors(monkeypatch):
    import litellm

    calls = []

    def timeout(**kwargs):
        calls.append(1)
        raise litellm.Timeout(
            message="secret key and source text", model="test", llm_provider="openai"
        )

    monkeypatch.setattr(litellm, "completion", timeout)
    monkeypatch.setattr("auditauthor.adapters.llm.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="temporarily unavailable") as error:
        LiteLLMClient(Settings(model_attempts=2)).generate(
            "system", "source", Extraction, "openai/test"
        )
    assert "secret" not in str(error.value)
    assert len(calls) == 2
