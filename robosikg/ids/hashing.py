from __future__ import annotations

import hashlib
from dataclasses import dataclass


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HashedURI:
    """A hashed, audit-friendly URI: urn:sha256:<hex>."""
    hex: str

    def uri(self) -> str:
        return f"urn:sha256:{self.hex}"


def hash_uri(canonical: str) -> HashedURI:
    return HashedURI(sha256_hex(canonical))


def edge_id(subject_uri: str, predicate_iri: str, object_uri: str) -> HashedURI:
    """Deterministic edge identity for reified edge metadata."""
    canon = f"{subject_uri}|{predicate_iri}|{object_uri}"
    return hash_uri(canon)
