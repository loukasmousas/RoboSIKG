from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


HASH_URI_RE = re.compile(r"^urn:sha256:[0-9a-f]{64}$")
IRI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:.+$")


class ReasoningSchemaError(ValueError):
    """Raised when reasoner output cannot be parsed or validated."""


class ReasoningInput(BaseModel):
    source_id: str
    frame_uri: str
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    sparql_snippets: dict[str, Any] = Field(default_factory=dict)
    ann_neighbors: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ReasoningClaim(BaseModel):
    type: str
    subject_uri: str
    predicate_iri: str
    object_uri: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}

    @field_validator("subject_uri", "object_uri")
    @classmethod
    def validate_hash_uri(cls, value: str) -> str:
        if not HASH_URI_RE.match(value):
            raise ValueError("URI must be of form urn:sha256:<64 lowercase hex chars>")
        return value

    @field_validator("predicate_iri")
    @classmethod
    def validate_iri(cls, value: str) -> str:
        if not IRI_RE.match(value):
            raise ValueError("predicate_iri must be an absolute IRI")
        return value


class TrajectoryPoint(BaseModel):
    point_2d: tuple[float, float]
    label: str

    model_config = {"extra": "forbid"}

    @field_validator("point_2d")
    @classmethod
    def validate_point_range(cls, value: tuple[float, float]) -> tuple[float, float]:
        x, y = value
        if x < 0.0 or x > 1000.0 or y < 0.0 or y > 1000.0:
            raise ValueError("trajectory point values must be normalized in [0, 1000]")
        return value


class ReasoningOutput(BaseModel):
    summary: str = Field(min_length=1)
    claims: list[ReasoningClaim] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    trajectory_2d_norm_0_1000: Optional[list[TrajectoryPoint]] = None

    model_config = {"extra": "forbid"}


def parse_reasoning_output(payload: str | dict[str, Any]) -> ReasoningOutput:
    try:
        if isinstance(payload, str):
            parsed = json.loads(payload)
        elif isinstance(payload, dict):
            parsed = payload
        else:
            raise ReasoningSchemaError("Reasoner payload must be a JSON string or dict")
    except json.JSONDecodeError as exc:
        raise ReasoningSchemaError(f"Reasoner returned invalid JSON: {exc}") from exc

    try:
        return ReasoningOutput.model_validate(parsed)
    except ValidationError as exc:
        raise ReasoningSchemaError(f"Reasoner JSON failed schema validation: {exc}") from exc
