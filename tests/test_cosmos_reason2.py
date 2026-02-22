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


def test_cosmos_reason2_normalizes_common_predicate_and_hash_formats(monkeypatch):
    import robosikg.reasoning.cosmos_reason2 as cmod

    digest_a = "a" * 64
    digest_b = "b" * 64
    content = {
        "summary": "frame-specific scene summary",
        "claims": [
            {
                "type": "relation",
                "subject_uri": digest_a,
                "predicate_iri": "near",
                "object_uri": f"urn:sha256:{digest_b.upper()}",
                "confidence": 87,
            }
        ],
        "suggested_queries": [],
    }
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}

    def _fake_post(_url: str, json: dict, timeout: float):  # noqa: A002
        return _FakeResponse(response)

    monkeypatch.setattr(cmod.requests, "post", _fake_post)

    client = CosmosReason2Client(base_url="http://example.test/v1", model="nvidia/cosmos-reason2-8b")
    out = client.reason(_rin())

    assert len(out.claims) == 1
    assert out.claims[0].subject_uri == f"urn:sha256:{digest_a}"
    assert out.claims[0].object_uri == f"urn:sha256:{digest_b}"
    assert out.claims[0].predicate_iri == "https://example.org/robosikg#near"
    assert out.claims[0].confidence == 0.87


def test_cosmos_reason2_accepts_alternate_claim_keys(monkeypatch):
    import robosikg.reasoning.cosmos_reason2 as cmod

    digest_a = "a" * 64
    digest_b = "b" * 64
    content = {
        "summary": "ok",
        "claims": [
            {
                "subject": f"urn:sha256:{digest_a}",
                "relation": "kg:inside",
                "object": f"urn:sha256:{digest_b}",
                "score": 0.42,
            }
        ],
        "suggested_queries": [],
    }
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}

    def _fake_post(_url: str, json: dict, timeout: float):  # noqa: A002
        return _FakeResponse(response)

    monkeypatch.setattr(cmod.requests, "post", _fake_post)

    client = CosmosReason2Client(base_url="http://example.test/v1", model="nvidia/cosmos-reason2-8b")
    out = client.reason(_rin())

    assert len(out.claims) == 1
    assert out.claims[0].predicate_iri == "https://example.org/robosikg#inside"
    assert out.claims[0].confidence == 0.42


def test_cosmos_reason2_captures_debug_payload(monkeypatch):
    import robosikg.reasoning.cosmos_reason2 as cmod

    digest_a = "a" * 64
    digest_b = "b" * 64
    content = {
        "summary": "ok",
        "claims": [
            {
                "subject": f"urn:sha256:{digest_a}",
                "relation": "kg:near",
                "object": f"urn:sha256:{digest_b}",
                "score": 0.33,
            }
        ],
        "suggested_queries": ["SELECT * WHERE { ?s ?p ?o } LIMIT 1"],
    }
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}

    def _fake_post(_url: str, json: dict, timeout: float):  # noqa: A002
        return _FakeResponse(response)

    monkeypatch.setattr(cmod.requests, "post", _fake_post)

    client = CosmosReason2Client(
        base_url="http://example.test/v1",
        model="nvidia/cosmos-reason2-8b",
        debug_capture=True,
    )
    out = client.reason(_rin())

    assert len(out.claims) == 1
    assert client.last_debug is not None
    assert client.last_debug["parse_mode"] == "lenient_coerce"
    assert client.last_debug["raw_claims_count"] == 1
    assert client.last_debug["coerced_claims_count"] == 1
    assert client.last_debug["final_claims_count"] == 1
