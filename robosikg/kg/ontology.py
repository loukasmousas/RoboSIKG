from __future__ import annotations

ONTOLOGY_TTL = """
@prefix kg: <https://example.org/robosikg#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

kg:Frame a kg:Class .
kg:Track a kg:Class .
kg:Region a kg:Class .
kg:Event a kg:Class .
kg:Edge a kg:Class .

kg:canon a kg:Property .
kg:sourceId a kg:Property .
kg:timeNs a kg:Property .
kg:frameIndex a kg:Property .
kg:cls a kg:Property .
kg:score a kg:Property .
kg:bboxX1 a kg:Property .
kg:bboxY1 a kg:Property .
kg:bboxX2 a kg:Property .
kg:bboxY2 a kg:Property .
kg:trackOf a kg:Property .
kg:seenIn a kg:Property .
kg:edgeSubject a kg:Property .
kg:edgePredicate a kg:Property .
kg:edgeObject a kg:Property .
kg:edgeConfidence a kg:Property .

kg:near a kg:Property .
kg:overlaps a kg:Property .
kg:inside a kg:Property .
"""
