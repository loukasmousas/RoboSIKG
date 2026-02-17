import pytest

from robosikg.reasoning.schemas import ReasoningSchemaError, parse_reasoning_output


def test_reasoning_schema_valid_payload():
    payload = {
        "summary": "ok",
        "claims": [
            {
                "type": "relation",
                "subject_uri": "urn:sha256:" + "a" * 64,
                "predicate_iri": "https://example.org/robosikg#near",
                "object_uri": "urn:sha256:" + "b" * 64,
                "confidence": 0.8,
            }
        ],
        "suggested_queries": ["SELECT * WHERE { ?s ?p ?o } LIMIT 1"],
        "trajectory_2d_norm_0_1000": [{"point_2d": [10, 20], "label": "step0"}],
    }
    parsed = parse_reasoning_output(payload)
    assert parsed.summary == "ok"
    assert len(parsed.claims) == 1
    assert parsed.claims[0].confidence == 0.8


def test_reasoning_schema_rejects_invalid_uri():
    payload = {
        "summary": "bad",
        "claims": [
            {
                "type": "relation",
                "subject_uri": "not-a-hash-uri",
                "predicate_iri": "https://example.org/robosikg#near",
                "object_uri": "urn:sha256:" + "b" * 64,
                "confidence": 0.8,
            }
        ],
        "suggested_queries": [],
    }
    with pytest.raises(ReasoningSchemaError):
        parse_reasoning_output(payload)
