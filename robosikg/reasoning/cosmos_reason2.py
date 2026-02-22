from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

from .schemas import HASH_URI_RE, IRI_RE, ReasoningInput, ReasoningOutput, ReasoningSchemaError, parse_reasoning_output

KG_BASE_IRI = "https://example.org/robosikg#"
_CANONICAL_PREDICATE_BY_ALIAS = {
    "near": "near",
    "close": "near",
    "close_to": "near",
    "adjacent": "near",
    "adjacent_to": "near",
    "next_to": "near",
    "inside": "inside",
    "in": "inside",
    "within": "inside",
    "contained_in": "inside",
    "overlap": "overlaps",
    "overlaps": "overlaps",
    "intersect": "overlaps",
    "intersects": "overlaps",
    "trackof": "trackOf",
    "track_of": "trackOf",
    "seenin": "seenIn",
    "seen_in": "seenIn",
}


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
        "no_claim_reason": {"type": ["string", "null"]},
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


def _safe_len(value: Any) -> int:
    if isinstance(value, (list, dict, str, tuple)):
        return len(value)
    return 0


def _trim_text(value: str, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars], True


def _normalize_hash_uri(value: Any, allowed_hash_uris: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    candidate: str | None = None
    if HASH_URI_RE.match(raw):
        candidate = raw
    else:
        lowered = raw.lower()
        if lowered.startswith("urn:sha256:"):
            digest = lowered[len("urn:sha256:") :]
            maybe = f"urn:sha256:{digest}"
            if HASH_URI_RE.match(maybe):
                candidate = maybe
        if candidate is None:
            match = re.search(r"[0-9a-f]{64}", raw, flags=re.IGNORECASE)
            if match:
                maybe = f"urn:sha256:{match.group(0).lower()}"
                if HASH_URI_RE.match(maybe):
                    candidate = maybe

    if candidate is None:
        return None

    if not allowed_hash_uris:
        return candidate
    return candidate if candidate in allowed_hash_uris else None


def _normalize_predicate_iri(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    token = raw
    if ":" in token:
        prefix, suffix = token.split(":", 1)
        if prefix.strip().lower() == "kg":
            token = suffix
        elif IRI_RE.match(raw):
            return raw
    elif IRI_RE.match(raw):
        return raw
    if "#" in token:
        token = token.rsplit("#", 1)[-1]
    if "/" in token:
        token = token.rsplit("/", 1)[-1]

    token = re.sub(r"[^a-zA-Z0-9]+", "_", token).strip("_").lower()
    if not token:
        return None

    canonical = _CANONICAL_PREDICATE_BY_ALIAS.get(token)
    if canonical is None:
        return None
    return f"{KG_BASE_IRI}{canonical}"


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

    tracks = rin.sparql_snippets.get("tracks")
    if isinstance(tracks, list):
        for row in tracks:
            if not isinstance(row, dict):
                continue
            cls = row.get("cls")
            if isinstance(cls, str) and cls.strip():
                out.add(cls.strip())

    track_motion = rin.sparql_snippets.get("track_motion")
    if isinstance(track_motion, list):
        for row in track_motion:
            if not isinstance(row, dict):
                continue
            cls = row.get("cls")
            if isinstance(cls, str) and cls.strip():
                out.add(cls.strip())

    return sorted(out)


def _coerce_reasoning_payload(raw: Any, rin: ReasoningInput) -> dict[str, Any]:
    if not isinstance(raw, dict):
        summary = str(raw).strip() if raw is not None else ""
        return {
            "summary": summary or f"NIM response for frame {rin.frame_uri}.",
            "claims": [],
            "no_claim_reason": "no_structured_payload",
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
    seen_claims: set[tuple[str, str, str, str]] = set()
    allowed_hash_uris = set(_collect_context_hash_uris(rin))
    raw_claims = raw.get("claims")
    if isinstance(raw_claims, list):
        for item in raw_claims:
            if not isinstance(item, dict):
                continue

            subject_uri = _normalize_hash_uri(
                item.get("subject_uri") or item.get("subject") or item.get("subject_id"),
                allowed_hash_uris,
            )
            object_uri = _normalize_hash_uri(
                item.get("object_uri") or item.get("object") or item.get("object_id"),
                allowed_hash_uris,
            )
            predicate_iri = _normalize_predicate_iri(
                item.get("predicate_iri") or item.get("predicate") or item.get("relation")
            )

            if subject_uri is None or object_uri is None or predicate_iri is None:
                continue
            if subject_uri == object_uri:
                continue

            claim_type = str(item.get("type") or item.get("relation") or "relation").strip() or "relation"
            dedupe_key = (subject_uri, predicate_iri, object_uri, claim_type)
            if dedupe_key in seen_claims:
                continue
            seen_claims.add(dedupe_key)

            claims.append(
                {
                    "type": claim_type,
                    "subject_uri": subject_uri,
                    "predicate_iri": predicate_iri,
                    "object_uri": object_uri,
                    "confidence": _normalize_confidence(item.get("confidence", item.get("score"))),
                }
            )

    no_claim_reason = raw.get("no_claim_reason")
    if not isinstance(no_claim_reason, str):
        no_claim_reason = None
    elif not no_claim_reason.strip():
        no_claim_reason = None
    else:
        no_claim_reason = no_claim_reason.strip()
    if claims:
        no_claim_reason = None
    elif no_claim_reason is None:
        no_claim_reason = "insufficient_evidence"

    return {
        "summary": summary,
        "claims": claims,
        "no_claim_reason": no_claim_reason,
        "suggested_queries": suggested_queries,
        "trajectory_2d_norm_0_1000": _normalize_trajectory(raw.get("trajectory_2d_norm_0_1000")),
    }


@dataclass
class CosmosReason2Client:
    base_url: str
    model: str
    timeout_s: float = 60.0
    debug_capture: bool = False
    debug_max_response_chars: int = 16000
    last_debug: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def reason(self, rin: ReasoningInput) -> ReasoningOutput:
        # OpenAI-compatible endpoint exposed by NIM for VLMs: POST /v1/chat/completions.
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        context_uris = _collect_context_hash_uris(rin)
        observed_classes = _collect_observed_classes(rin)
        debug: dict[str, Any] = {
            "url": url,
            "model": self.model,
            "frame_uri": rin.frame_uri,
            "context_counts": {
                "allowed_entity_uris": len(context_uris),
                "observed_classes": len(observed_classes),
                "recent_events": len(rin.recent_events),
                "ann_neighbors": len(rin.ann_neighbors),
                "sparql_snippets_keys": len(rin.sparql_snippets),
            },
            "ann_neighbors_preview": [
                {
                    "uri": str(row.get("uri")),
                    "score": row.get("score"),
                    "meta_cls": row.get("meta", {}).get("cls") if isinstance(row.get("meta"), dict) else None,
                    "meta_frame_uri": row.get("meta", {}).get("frame_uri")
                    if isinstance(row.get("meta"), dict)
                    else None,
                }
                for row in rin.ann_neighbors[:5]
                if isinstance(row, dict)
            ],
        }

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
                "Summary must be concise (max 2 sentences) and specific to the current frame context.",
                "If you suggest a 2D trajectory, output points in normalized 0-1000 coordinates per axis.",
                "Reference entities only by hashed URIs present in the context.",
                "For predicate_iri, use absolute IRIs under https://example.org/robosikg# (near, inside, overlaps, trackOf, seenIn).",
                "Do not mention object classes outside observed_classes when that list is non-empty.",
                "When at least two allowed_entity_uris are present, include 1-5 claims whenever evidence supports it.",
                "If claims is empty, set no_claim_reason to a concise cause such as insufficient_evidence, single_entity, or ambiguous_relations.",
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

        try:
            resp = requests.post(url, json=body, timeout=self.timeout_s)
            resp.raise_for_status()
            data = resp.json()
            content = _extract_content(data)
            text, was_truncated = _trim_text(content, self.debug_max_response_chars)

            parsed_for_debug = _load_json_lenient(content)
            raw_claims_count = 0
            if isinstance(parsed_for_debug, dict):
                raw_claims_count = _safe_len(parsed_for_debug.get("claims"))

            debug.update(
                {
                    "http_status": getattr(resp, "status_code", None),
                    "response_content_len": len(content),
                    "response_content_truncated": was_truncated,
                    "response_content_text": text,
                    "raw_claims_count": raw_claims_count,
                    "raw_no_claim_reason": parsed_for_debug.get("no_claim_reason")
                    if isinstance(parsed_for_debug, dict)
                    else None,
                }
            )

            try:
                out = parse_reasoning_output(content)
                debug.update(
                    {
                        "parse_mode": "strict",
                        "strict_schema_ok": True,
                        "lenient_json_ok": parsed_for_debug is not None,
                        "coerced_claims_count": None,
                        "final_claims_count": len(out.claims),
                        "final_no_claim_reason": out.no_claim_reason,
                        "final_suggested_queries_count": len(out.suggested_queries),
                        "final_trajectory_points_count": 0
                        if out.trajectory_2d_norm_0_1000 is None
                        else len(out.trajectory_2d_norm_0_1000),
                    }
                )
                return out
            except ReasoningSchemaError as exc:
                coerced = _coerce_reasoning_payload(
                    parsed_for_debug if parsed_for_debug is not None else content,
                    rin,
                )
                out = parse_reasoning_output(coerced)
                debug.update(
                    {
                        "parse_mode": "lenient_coerce",
                        "strict_schema_ok": False,
                        "strict_schema_error": str(exc),
                        "lenient_json_ok": parsed_for_debug is not None,
                        "coerced_claims_count": _safe_len(coerced.get("claims")),
                        "final_claims_count": len(out.claims),
                        "final_no_claim_reason": out.no_claim_reason,
                        "final_suggested_queries_count": len(out.suggested_queries),
                        "final_trajectory_points_count": 0
                        if out.trajectory_2d_norm_0_1000 is None
                        else len(out.trajectory_2d_norm_0_1000),
                    }
                )
                return out
        except Exception as exc:
            debug.update({"error": f"{type(exc).__name__}: {exc}"})
            raise
        finally:
            self.last_debug = debug if self.debug_capture else None
