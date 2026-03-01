# SPARQL Query Playbook (Traffic + Balloons)

This document provides tested SPARQL examples for the current `out_traffic` and `out_balloons` outputs.

The goal is:
- one **general insight** query per video
- one **frame-specific** query per video
- clear explanation of what each query returns

## Notes About Current Runs

- `out_traffic` has only `kg:near` edges, and they are mostly retrieval-driven fallback claims.
- `out_balloons` has a mix of `kg:near`, `kg:inside`, `kg:trackOf`, and `kg:seenIn` edges.
- Some `kg:near` edges are not same-frame pairs, so frame-constrained queries should use `OPTIONAL` near joins when needed.

## Traffic: General Insight

Use this to summarize dominant proximity patterns by class pair.

```sparql
PREFIX kg: <https://example.org/robosikg#>
SELECT ?srcCls ?dstCls
       (COUNT(?e) AS ?nearEdges)
       (ROUND(AVG(?conf) * 1000) / 1000 AS ?avgConfidence)
WHERE {
  ?e a kg:Edge ;
     kg:edgePredicate kg:near ;
     kg:edgeSubject ?s ;
     kg:edgeObject ?o ;
     kg:edgeConfidence ?conf .
  OPTIONAL { ?s kg:cls ?sClsRaw }
  OPTIONAL { ?o kg:cls ?oClsRaw }
  BIND(COALESCE(?sClsRaw, "n/a") AS ?srcCls)
  BIND(COALESCE(?oClsRaw, "n/a") AS ?dstCls)
}
GROUP BY ?srcCls ?dstCls
ORDER BY DESC(?nearEdges) DESC(?avgConfidence)
LIMIT 12
```

What it shows:
- `srcCls`, `dstCls`: class pair at each end of `near`
- `nearEdges`: how often that pair appears
- `avgConfidence`: mean edge confidence for that pair

## Traffic: Specific Frame Drill-Down

Use this to focus all UI panels on one frame and inspect concrete near interactions.
Current tested frame: `90`.

```sparql
PREFIX kg: <https://example.org/robosikg#>
SELECT ?frameUri ?frameIdx ?s ?sCls ?o ?oCls ?conf
       ?sx1 ?sy1 ?sx2 ?sy2 ?ox1 ?oy1 ?ox2 ?oy2
WHERE {
  VALUES ?targetFrameIdx { 90 }
  ?frameUri a kg:Frame ; kg:frameIndex ?frameIdx .
  FILTER(?frameIdx = ?targetFrameIdx)

  ?e a kg:Edge ;
     kg:edgePredicate kg:near ;
     kg:edgeSubject ?s ;
     kg:edgeObject ?o ;
     kg:edgeConfidence ?conf .

  ?s kg:seenIn ?frameUri ; kg:cls ?sCls ;
     kg:bboxX1 ?sx1 ; kg:bboxY1 ?sy1 ; kg:bboxX2 ?sx2 ; kg:bboxY2 ?sy2 .
  ?o kg:seenIn ?frameUri ; kg:cls ?oCls ;
     kg:bboxX1 ?ox1 ; kg:bboxY1 ?oy1 ; kg:bboxX2 ?ox2 ; kg:bboxY2 ?oy2 .
}
ORDER BY DESC(?conf)
LIMIT 25
```

What it shows:
- one frame (`?frameIdx`)
- interacting objects (`?s`, `?o`) and classes
- edge confidence
- both boxes (`s*` and `o*`) for overlay/debugging

## Balloons: General Insight

Use this to get a broad predicate/class interaction map.

```sparql
PREFIX kg: <https://example.org/robosikg#>
SELECT ?predicate ?subjectCls ?objectCls
       (COUNT(?e) AS ?edgeCount)
       (ROUND(AVG(?confidence) * 1000) / 1000 AS ?avgConfidence)
WHERE {
  ?e a kg:Edge ;
     kg:edgePredicate ?predicate ;
     kg:edgeSubject ?s ;
     kg:edgeObject ?o ;
     kg:edgeConfidence ?confidence .
  OPTIONAL { ?s kg:cls ?sClsRaw }
  OPTIONAL { ?o kg:cls ?oClsRaw }
  BIND(COALESCE(?sClsRaw, "n/a") AS ?subjectCls)
  BIND(COALESCE(?oClsRaw, "n/a") AS ?objectCls)
}
GROUP BY ?predicate ?subjectCls ?objectCls
ORDER BY DESC(?edgeCount) DESC(?avgConfidence)
LIMIT 20
```

What it shows:
- predicate mix (`near`, `inside`, etc.)
- class pairs for each predicate
- volume and confidence quality

## Balloons: Specific Frame Drill-Down

This query is robust for the current graph shape: it anchors on frame regions first, then joins near edges in either direction as optional context.
Current tested frame: `462`.

```sparql
PREFIX kg: <https://example.org/robosikg#>
SELECT ?frameUri ?frameIdx ?airObj ?airCls ?nearObj ?nearCls ?nearConf
       ?x1 ?y1 ?x2 ?y2
WHERE {
  VALUES ?targetFrameIdx { 462 }
  ?frameUri a kg:Frame ; kg:frameIndex ?frameIdx .
  FILTER(?frameIdx = ?targetFrameIdx)

  ?airObj a kg:Region ;
          kg:seenIn ?frameUri ;
          kg:cls ?airCls ;
          kg:bboxX1 ?x1 ; kg:bboxY1 ?y1 ; kg:bboxX2 ?x2 ; kg:bboxY2 ?y2 .
  FILTER(REGEX(LCASE(STR(?airCls)), "balloon|kite|bird|sports ball|ball"))

  OPTIONAL {
    ?eOut a kg:Edge ;
          kg:edgePredicate kg:near ;
          kg:edgeSubject ?airObj ;
          kg:edgeObject ?nearOut ;
          kg:edgeConfidence ?confOut .
    ?nearOut kg:seenIn ?frameUri ; kg:cls ?nearOutCls .
  }
  OPTIONAL {
    ?eIn a kg:Edge ;
         kg:edgePredicate kg:near ;
         kg:edgeSubject ?nearIn ;
         kg:edgeObject ?airObj ;
         kg:edgeConfidence ?confIn .
    ?nearIn kg:seenIn ?frameUri ; kg:cls ?nearInCls .
  }

  BIND(COALESCE(?nearOut, ?nearIn) AS ?nearObj)
  BIND(COALESCE(?nearOutCls, ?nearInCls, "n/a") AS ?nearCls)
  BIND(COALESCE(?confOut, ?confIn) AS ?nearConf)
}
ORDER BY ?frameIdx DESC(?nearConf)
LIMIT 80
```

What it shows:
- all relevant air-like objects in one frame
- their bounding boxes
- optional near partner and confidence, whether relation is outgoing or incoming

## Why The Previous Balloons Frame Query Returned Zero

The earlier query required:
- `kg:near` with the air object specifically on the **subject** side
- both endpoints tied to the **same frame** in that join pattern

In the current run, many `near` edges do not satisfy that exact directional/same-frame shape for the filtered classes.
The revised frame query above avoids this by:
- anchoring from frame regions first
- checking `near` in both directions via `OPTIONAL`

