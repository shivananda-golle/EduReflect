import json
import threading
from typing import List

import numpy as np
import faiss
from fastembed import TextEmbedding

from app.utils.config import EMBEDDING_MODEL, INDEX_DIR

FAISS_INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"

_model = None
_index = None
_metadata = None
_load_lock = threading.Lock()


def _lazy_load():
    with _load_lock:
        return _load()


def _load():
    global _model, _index, _metadata
    if _model is None:
        # ONNX runtime model (no PyTorch): small enough for free hosting tiers
        _model = TextEmbedding(EMBEDDING_MODEL)
    if _index is None:
        if not FAISS_INDEX_PATH.exists():
            return False
        _index = faiss.read_index(str(FAISS_INDEX_PATH))
    if _metadata is None:
        if not METADATA_PATH.exists():
            return False
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _metadata = json.load(f)
    return True


def embed_query(question: str) -> np.ndarray:
    # query_embed adds the model's retrieval instruction prefix
    vector = np.array(list(_model.query_embed([question])), dtype="float32")
    faiss.normalize_L2(vector)
    return vector


def retrieve_from_kb(question: str, top_k: int = 3) -> List[str]:
    """
    Retrieve top-k relevant chunks from the local knowledge base.
    Returns the chunk texts.
    """
    ok = _lazy_load()
    if not ok:
        return []

    scores, indices = _index.search(embed_query(question), top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append(_metadata[idx]["text"])
    return results
