from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from .schemas import ReasoningInput, ReasoningOutput, parse_reasoning_output


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


@dataclass
class CosmosReason2Client:
    base_url: str
    model: str
    timeout_s: float = 60.0

    def reason(self, rin: ReasoningInput) -> ReasoningOutput:
        # OpenAI-compatible endpoint exposed by NIM for VLMs: POST /v1/chat/completions.
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        user_payload = {
            "schema": PROMPT_SCHEMA,
            "context": {
                "source_id": rin.source_id,
                "frame_uri": rin.frame_uri,
                "recent_events": rin.recent_events,
                "sparql_snippets": rin.sparql_snippets,
                "ann_neighbors": rin.ann_neighbors,
            },
            "instructions": [
                "If you suggest a 2D trajectory, output points in normalized 0-1000 coordinates per axis.",
                "Reference entities only by hashed URIs present in the context.",
                "Do not output markdown; output JSON only.",
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
        return parse_reasoning_output(content)
