from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from .schemas import HASH_URI_RE, IRI_RE, ReasoningInput, ReasoningOutput, ReasoningSchemaError, parse_reasoning_output


PROMPT_SYSTEM = (
    "You are a robotics physical-reasoning assistant. "
    "You will be given a structured memory context from a robot perception system. "
    "Return ONLY JSON that matches the provided schema."
)

PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "subject_uri": {"type": "string"},
                    "predicate_iri": {"type": "string"},
                    "object_uri": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["type", "subject_uri", "predicate_iri", "object_uri", "confidence"],
            },
        },
        "suggested_queries": {"type": "array", "items": {"type": "string"}},
        "trajectory_2d_norm_0_1000": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "point_2d": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "label": {"type": "string"},
                },
                "required": ["point_2d", "label"],
            },
        },
    },
    "required": ["summary", "claims", "suggested_queries"],
}


def _extract_content(response_json: dict[str, Any]) -> str:
    try:
        content: Any = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("NIM response did not include a valid choices[0].message.content field") from exc

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        merged = "\n".join(parts).strip()
        if merged:
            return merged

    raise RuntimeError("NIM response content was not a JSON string")


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_str = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _load_json_lenient(content: str) -> Any:
    text = content.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fence_match:
        fenced = fence_match.group(1).strip()
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            candidate = _extract_balanced_json_object(fenced)
            if candidate is not None:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

    candidate = _extract_balanced_json_object(text)
    if candidate is not None:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return None


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _collect_context_hash_uris(rin: ReasoningInput) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add_if_hash_uri(value: str | None) -> None:
        if not isinstance(value, str):
            return
        if not HASH_URI_RE.match(value):
            return
        if value in seen:
            return
        seen.add(value)
        out.append(value)

    add_if_hash_uri(rin.frame_uri)
    for s in _iter_strings(rin.recent_events):
        add_if_hash_uri(s)
    for s in _iter_strings(rin.sparql_snippets):
        add_if_hash_uri(s)
    for s in _iter_strings(rin.ann_neighbors):
        add_if_hash_uri(s)
    return out


def _normalize_confidence(value: Any) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.5
    if conf > 1.0 and conf <= 100.0:
        conf /= 100.0
    if conf < 0.0:
        return 0.0
    if conf > 1.0:
        return 1.0
    return conf


def _normalize_trajectory(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    points: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        point = item.get("point_2d")
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError):
            continue
        x = min(1000.0, max(0.0, x))
        y = min(1000.0, max(0.0, y))
        label = str(item.get("label") or f"p{idx}")
        points.append({"point_2d": [x, y], "label": label})
    return points or None


def _collect_observed_classes(rin: ReasoningInput) -> list[str]:
    out: set[str] = set()

    for row in rin.ann_neighbors:
        if not isinstance(row, dict):
            continue
        meta = row.get("meta")
        if isinstance(meta, dict):
            cls = meta.get("cls")
            if isinstance(cls, str) and cls.strip():
                out.add(cls.strip())

    for s in _iter_strings(rin.sparql_snippets):
        if isinstance(s, str):
            cls = s.strip()
            if cls:
                out.add(cls)

    return sorted(out)


def _coerce_reasoning_payload(raw: Any, rin: ReasoningInput) -> dict[str, Any]:
    if not isinstance(raw, dict):
        summary = str(raw).strip() if raw is not None else ""
        return {
            "summary": summary or f"NIM response for frame {rin.frame_uri}.",
            "claims": [],
            "suggested_queries": [],
            "trajectory_2d_norm_0_1000": None,
        }

    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = f"NIM response for frame {rin.frame_uri}."
    else:
        summary = summary.strip()

    suggested_queries: list[str] = []
    raw_queries = raw.get("suggested_queries")
    if isinstance(raw_queries, list):
        for q in raw_queries:
            if isinstance(q, str):
                qq = q.strip()
                if qq:
                    suggested_queries.append(qq)

    claims: list[dict[str, Any]] = []
    raw_claims = raw.get("claims")
    if isinstance(raw_claims, list):
        for item in raw_claims:
            if not isinstance(item, dict):
                continue

            subject_uri = item.get("subject_uri")
            predicate_iri = item.get("predicate_iri")
            object_uri = item.get("object_uri")
            if not isinstance(subject_uri, str) or not HASH_URI_RE.match(subject_uri):
                continue
            if not isinstance(object_uri, str) or not HASH_URI_RE.match(object_uri):
                continue
            if not isinstance(predicate_iri, str) or not IRI_RE.match(predicate_iri):
                continue

            claim_type = str(item.get("type") or "relation")
            claims.append(
                {
                    "type": claim_type,
                    "subject_uri": subject_uri,
                    "predicate_iri": predicate_iri,
                    "object_uri": object_uri,
                    "confidence": _normalize_confidence(item.get("confidence")),
                }
            )

    return {
        "summary": summary,
        "claims": claims,
        "suggested_queries": suggested_queries,
        "trajectory_2d_norm_0_1000": _normalize_trajectory(raw.get("trajectory_2d_norm_0_1000")),
    }


@dataclass
class CosmosReason2Client:
    base_url: str
    model: str
    timeout_s: float = 60.0

    def reason(self, rin: ReasoningInput) -> ReasoningOutput:
        # OpenAI-compatible endpoint exposed by NIM for VLMs: POST /v1/chat/completions.
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        context_uris = _collect_context_hash_uris(rin)
        observed_classes = _collect_observed_classes(rin)

        user_payload = {
            "schema": PROMPT_SCHEMA,
            "context": {
                "source_id": rin.source_id,
                "frame_uri": rin.frame_uri,
                "allowed_entity_uris": context_uris,
                "observed_classes": observed_classes,
                "recent_events": rin.recent_events,
                "sparql_snippets": rin.sparql_snippets,
                "ann_neighbors": rin.ann_neighbors,
            },
            "instructions": [
                "If you suggest a 2D trajectory, output points in normalized 0-1000 coordinates per axis.",
                "Reference entities only by hashed URIs present in the context.",
                "Do not mention object classes outside observed_classes when that list is non-empty.",
                "Do not output markdown; output JSON only.",
                "If uncertain, return an empty claims array instead of guessed entities.",
            ],
        }

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": PROMPT_SYSTEM},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "temperature": 0.0,
            "max_tokens": 2000,
            "stream": False,
        }

        resp = requests.post(url, json=body, timeout=self.timeout_s)
        resp.raise_for_status()
        data = resp.json()
        content = _extract_content(data)

        try:
            return parse_reasoning_output(content)
        except ReasoningSchemaError:
            parsed = _load_json_lenient(content)
            coerced = _coerce_reasoning_payload(parsed if parsed is not None else content, rin)
            return parse_reasoning_output(coerced)
