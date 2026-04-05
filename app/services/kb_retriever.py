import json
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

INDEX_DIR = Path("data/index")
FAISS_INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"

_model = None
_index = None
_metadata = None


def _lazy_load():
    global _model, _index, _metadata
    if _model is None:
        _model = SentenceTransformer("intfloat/e5-base")
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


def retrieve_from_kb(question: str, top_k: int = 3) -> List[str]:
    """
    Retrieve top-k relevant chunks from the local knowledge base.
    Returns the chunk texts.
    """
    ok = _lazy_load()
    if not ok:
        return []

    query_embedding = _model.encode(f"query: {question}", normalize_embeddings=True)

    scores, indices = _index.search(np.array([query_embedding]), top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append(_metadata[idx]["text"])
    return results