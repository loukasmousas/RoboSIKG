from robosikg.kg.store import GraphStore

def test_kg_add_and_query():
    s = GraphStore()
    f = "urn:sha256:" + "0"*64
    s.add_frame(f, "src", 0, 123)
    rows = s.query("""
    PREFIX kg: <https://example.org/robosikg#>
    SELECT ?f WHERE { ?f a kg:Frame . }
    """)
    assert len(rows) >= 1
