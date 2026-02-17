from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from robosikg.ids.hashing import edge_id, sha256_hex
from .ontology import ONTOLOGY_TTL


@dataclass
class GraphStore:
    base_iri: str = "https://example.org/robosikg#"

    def __post_init__(self) -> None:
        self.g = Graph()
        self.KG = Namespace(self.base_iri)
        self.g.bind("kg", self.KG)
        self._load_ontology()
        # Hash-indexed “UI mirror” equivalent (fast lookup), modeled after your SIKG design pattern.
        self.metadata_index: dict[str, dict[str, Any]] = {}

    def _load_ontology(self) -> None:
        self.g.parse(data=ONTOLOGY_TTL, format="turtle")

    def _idx_put(self, uri: str, payload: dict[str, Any]) -> None:
        self.metadata_index[sha256_hex(uri)] = {"uri": uri, **payload}

    def add_frame(self, frame_uri: str, source_id: str, frame_index: int, t_ns: int) -> None:
        u = URIRef(frame_uri)
        self.g.add((u, RDF.type, self.KG.Frame))
        self.g.add((u, self.KG.sourceId, Literal(source_id)))
        self.g.add((u, self.KG.frameIndex, Literal(frame_index, datatype=XSD.integer)))
        self.g.add((u, self.KG.timeNs, Literal(t_ns, datatype=XSD.integer)))
        self._idx_put(frame_uri, {"type": "Frame", "sourceId": source_id, "frameIndex": frame_index, "timeNs": t_ns})

    def add_track(self, track_uri: str, source_id: str, track_id: int, cls: str) -> None:
        u = URIRef(track_uri)
        self.g.add((u, RDF.type, self.KG.Track))
        self.g.add((u, self.KG.sourceId, Literal(source_id)))
        self.g.add((u, self.KG.cls, Literal(cls)))
        self._idx_put(track_uri, {"type": "Track", "sourceId": source_id, "trackId": track_id, "cls": cls})

    def add_region(
        self,
        region_uri: str,
        frame_uri: str,
        cls: str,
        score: float,
        bbox_xyxy: tuple[int, int, int, int],
        track_uri: Optional[str] = None,
    ) -> None:
        x1, y1, x2, y2 = bbox_xyxy
        u = URIRef(region_uri)
        self.g.add((u, RDF.type, self.KG.Region))
        self.g.add((u, self.KG.seenIn, URIRef(frame_uri)))
        self.g.add((u, self.KG.cls, Literal(cls)))
        self.g.add((u, self.KG.score, Literal(score, datatype=XSD.float)))
        self.g.add((u, self.KG.bboxX1, Literal(x1, datatype=XSD.integer)))
        self.g.add((u, self.KG.bboxY1, Literal(y1, datatype=XSD.integer)))
        self.g.add((u, self.KG.bboxX2, Literal(x2, datatype=XSD.integer)))
        self.g.add((u, self.KG.bboxY2, Literal(y2, datatype=XSD.integer)))
        if track_uri is not None:
            self.g.add((u, self.KG.trackOf, URIRef(track_uri)))
        self._idx_put(region_uri, {"type": "Region", "frame": frame_uri, "cls": cls, "score": score, "bbox": bbox_xyxy, "track": track_uri})

    def add_edge(self, s_uri: str, p_iri: str, o_uri: str, confidence: float = 1.0) -> str:
        """
        Adds the triple (s p o) AND a reified Edge node for auditable metadata.
        The Edge URI is deterministic sha256(s|p|o).
        """
        edge = edge_id(s_uri, p_iri, o_uri).uri()
        e = URIRef(edge)
        self.g.add((URIRef(s_uri), URIRef(p_iri), URIRef(o_uri)))
        self.g.add((e, RDF.type, self.KG.Edge))
        self.g.add((e, self.KG.edgeSubject, URIRef(s_uri)))
        self.g.add((e, self.KG.edgePredicate, URIRef(p_iri)))
        self.g.add((e, self.KG.edgeObject, URIRef(o_uri)))
        self.g.add((e, self.KG.edgeConfidence, Literal(float(confidence), datatype=XSD.float)))
        self._idx_put(edge, {"type": "Edge", "s": s_uri, "p": p_iri, "o": o_uri, "confidence": confidence})
        return edge

    def query(self, sparql: str) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        q = self.g.query(sparql)
        for r in q:
            rows.append({str(var): str(val) for var, val in r.asdict().items()})
        return rows

    def serialize_ttl(self) -> str:
        return self.g.serialize(format="turtle")

    def serialize_ntriples_sorted(self) -> str:
        data = self.g.serialize(format="nt")
        lines = [line.strip() for line in data.splitlines() if line.strip()]
        lines.sort()
        return "\n".join(lines) + ("\n" if lines else "")

    def triple_count(self) -> int:
        return len(self.g)

    def search_uri_fast(self, uri: str) -> Optional[dict[str, Any]]:
        return self.metadata_index.get(sha256_hex(uri))
