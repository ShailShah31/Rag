from contextlib import nullcontext
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from repo_rag import cli
from repo_rag.answer import NOT_FOUND, generate
from repo_rag.chunks import Chunk
from repo_rag.config import RagError, Settings
from repo_rag.index import Hit


HITS = [Hit(Chunk("src/a.py", 2, 3, "python", "def a():\n    return 1"), 0.2)]
CFG = replace(Settings(), api_key="test-only", api_model="fake-model")


class APIError(Exception):
    pass


class ConnectionError(APIError):
    pass


class StatusError(APIError):
    def __init__(self, code):
        super().__init__("provider details are private")
        self.status_code = code


def fake_sdk(*outcomes):
    pending = iter(outcomes)
    requests = []

    def create(**request):
        requests.append(request)
        outcome = next(pending)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=outcome)]
        )

    def client(**kwargs):
        assert kwargs["max_retries"] == 0
        return nullcontext(SimpleNamespace(messages=SimpleNamespace(create=create)))

    return SimpleNamespace(
        Anthropic=client, APIError=APIError, APIConnectionError=ConnectionError,
        APIStatusError=StatusError,
    ), requests


def test_generation_retries_and_renders_citation():
    raw = '{"claims":[{"text":"The function returns 1.","citations":["src/a.py:2-3"]}]}'
    sdk, requests = fake_sdk(ConnectionError(), StatusError(429), raw)
    delays = []
    assert generate("What does a return?", HITS, CFG, sdk=sdk, sleep=delays.append) == (
        "- The function returns 1. [src/a.py:2-3]"
    )
    assert delays == [1, 2]
    assert requests[-1]["model"] == "fake-model"
    payload = json.loads(requests[-1]["messages"][0]["content"])
    assert payload["passages"][0]["citation"] == "src/a.py:2-3"
    assert "untrusted" in requests[-1]["system"]


def test_insufficient_and_fabricated_citation():
    sdk, _ = fake_sdk(NOT_FOUND)
    assert generate("Unknown?", HITS, CFG, sdk=sdk) == NOT_FOUND
    sdk, _ = fake_sdk('{"claims":[{"text":"Made up","citations":["other.py:1-2"]}]}')
    with pytest.raises(RagError, match="uncited"):
        generate("Unknown?", HITS, CFG, sdk=sdk)


def test_auth_failure_is_not_retried_or_leaked():
    sdk, requests = fake_sdk(StatusError(401))
    with pytest.raises(RagError, match="denied access") as error:
        generate("Question?", HITS, CFG, sdk=sdk)
    assert len(requests) == 1
    assert "provider details" not in str(error.value)


def test_missing_api_key():
    with pytest.raises(RagError, match="ANTHROPIC_API_KEY"):
        generate("Question?", HITS, replace(CFG, api_key=""))


def test_no_relevant_results_does_not_call_api(repo, monkeypatch, capsys):
    monkeypatch.setenv("REPO_RAG_MAX_DISTANCE", "0.1")
    monkeypatch.setattr(cli, "Index", lambda cfg: SimpleNamespace(retrieve=lambda *args: HITS))

    def unexpected(*args):
        pytest.fail("Generation should not run without relevant results")

    monkeypatch.setattr(cli, "generate", unexpected)
    assert cli.main(["ask", str(repo), "What happened?"]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == NOT_FOUND
    assert "cosine distance cutoff" in output.err
