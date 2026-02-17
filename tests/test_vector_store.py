import numpy as np

from robosikg.vector.faiss_store import FaissVectorStore


def test_faiss_store_add_and_search_roundtrip():
    store = FaissVectorStore(dim=4, use_gpu=False)
    vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    store.add(uri="urn:sha256:" + "c" * 64, vec=vec, meta={"k": "v"})
    out = store.search(query=vec, k=1)
    assert len(out) == 1
    assert out[0]["uri"] == "urn:sha256:" + "c" * 64
    assert out[0]["meta"]["k"] == "v"
