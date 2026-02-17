from __future__ import annotations

from robosikg.kg.store import GraphStore


def q_tracks(store: GraphStore) -> list[dict[str, str]]:
    return store.query("""
    PREFIX kg: <https://example.org/robosikg#>
    SELECT ?t ?cls WHERE {
      ?t a kg:Track ;
         kg:cls ?cls .
    } ORDER BY ?t
    """)


def q_recent_regions(store: GraphStore, limit: int = 25) -> list[dict[str, str]]:
    return store.query(f"""
    PREFIX kg: <https://example.org/robosikg#>
    SELECT ?r ?frame ?cls ?score WHERE {{
      ?r a kg:Region ;
         kg:seenIn ?frame ;
         kg:cls ?cls ;
         kg:score ?score .
    }} ORDER BY DESC(?score) LIMIT {int(limit)}
    """)
