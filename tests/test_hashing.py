from robosikg.ids.hashing import sha256_hex, hash_uri, edge_id

def test_sha256_len():
    h = sha256_hex("abc")
    assert len(h) == 64

def test_hash_uri_format():
    u = hash_uri("frame:x:1:2").uri()
    assert u.startswith("urn:sha256:")

def test_edge_id_deterministic():
    e1 = edge_id("urn:sha256:a", "https://example.org/p", "urn:sha256:b").uri()
    e2 = edge_id("urn:sha256:a", "https://example.org/p", "urn:sha256:b").uri()
    assert e1 == e2
