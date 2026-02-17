from __future__ import annotations

from dataclasses import dataclass

from .schemas import ReasoningInput, ReasoningOutput


@dataclass
class MockReasoner:
    def reason(self, rin: ReasoningInput) -> ReasoningOutput:
        # Deterministic stub: no external calls.
        return ReasoningOutput.model_validate(
            {
                "summary": f"Mock summary for {rin.frame_uri} with {len(rin.ann_neighbors)} neighbors.",
                "claims": [],
                "suggested_queries": [
                    "PREFIX kg: <https://example.org/robosikg#> SELECT ?r WHERE { ?r a kg:Region } LIMIT 10"
                ],
                "trajectory_2d_norm_0_1000": None,
            }
        )
