from __future__ import annotations

import json

from robosikg.reasoning.cosmos_reason2 import CosmosReason2Client
from robosikg.reasoning.schemas import ReasoningInput


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _rin() -> ReasoningInput:
    return ReasoningInput(
        source_id="demo",
        frame_uri="urn:sha256:" + "a" * 64,
        recent_events=[],
        sparql_snippets={},
        ann_neighbors=[
            {"uri": "urn:sha256:" + "b" * 64, "score": 0.5, "meta": {"frame_uri": "urn:sha256:" + "c" * 64}}
        ],
    )


def test_cosmos_reason2_coerces_invalid_claim_payload(monkeypatch):
    import robosikg.reasoning.cosmos_reason2 as cmod

    content = {
        "summary": "Objects likely interacting",
        "claims": [
            {
                "type": "contact",
                "subject_uri": "robot",
                "predicate_iri": "near",
                "object_uri": "table",
            }
        ],
        "suggested_queries": ["SELECT ?x WHERE { ?x ?p ?o } LIMIT 3"],
    }
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}

    def _fake_post(_url: str, json: dict, timeout: float):  # noqa: A002
        assert timeout == 30.0
        assert json["model"] == "nvidia/cosmos-reason2-8b"
        return _FakeResponse(response)

    monkeypatch.setattr(cmod.requests, "post", _fake_post)

    client = CosmosReason2Client(
        base_url="http://example.test/v1",
        model="nvidia/cosmos-reason2-8b",
        timeout_s=30.0,
    )
    out = client.reason(_rin())

    assert out.summary == "Objects likely interacting"
    assert out.claims == []


def test_cosmos_reason2_coerces_non_json_content(monkeypatch):
    import robosikg.reasoning.cosmos_reason2 as cmod

    response = {"choices": [{"message": {"content": "not json response from model"}}]}

    def _fake_post(_url: str, json: dict, timeout: float):  # noqa: A002
        return _FakeResponse(response)

    monkeypatch.setattr(cmod.requests, "post", _fake_post)

    client = CosmosReason2Client(base_url="http://example.test/v1", model="nvidia/cosmos-reason2-8b")
    out = client.reason(_rin())

    assert out.summary == "not json response from model"
    assert out.claims == []
    assert out.suggested_queries == []
