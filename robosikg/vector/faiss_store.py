from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


@dataclass
class FaissVectorStore:
    dim: int
    use_gpu: bool = False
    _index: Any = None
    _next_id: int = 1
    id_to_uri: dict[int, str] = field(default_factory=dict)
    payload: dict[int, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if faiss is None:
            raise RuntimeError("faiss is not installed. Install faiss-cpu (pip) for the starter.")
        base = faiss.IndexFlatIP(self.dim)
        self._index = faiss.IndexIDMap2(base)

    def add(self, uri: str, vec: np.ndarray, meta: dict[str, Any]) -> int:
        if vec.dtype != np.float32:
            vec = vec.astype(np.float32)
        vec = vec.reshape(1, -1)
        idx = self._next_id
        self._next_id += 1
        self._index.add_with_ids(vec, np.array([idx], dtype=np.int64))
        self.id_to_uri[idx] = uri
        self.payload[idx] = meta
        return idx

    def search(self, query: np.ndarray, k: int = 5) -> list[dict[str, Any]]:
        if query.dtype != np.float32:
            query = query.astype(np.float32)
        q = query.reshape(1, -1)
        scores, ids = self._index.search(q, k)
        out: list[dict[str, Any]] = []
        for s, i in zip(scores[0].tolist(), ids[0].tolist()):
            if i == -1:
                continue
            out.append({"id": i, "score": float(s), "uri": self.id_to_uri[i], "meta": self.payload.get(i, {})})
        return out

    def count(self) -> int:
        return len(self.id_to_uri)
