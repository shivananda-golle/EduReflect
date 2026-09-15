"""
Knowledge-base retrieval.

Modes (RETRIEVAL_MODE):
- dense:         bge-small embeddings + FAISS cosine similarity
- bm25:          keyword search (good for names, formulas and terms)
- hybrid:        dense and BM25 rankings merged with reciprocal rank fusion
- hybrid_rerank: hybrid candidates re-scored by a small cross-encoder
"""
import json
import math
import re
import threading
from collections import Counter
from typing import Dict, List, Optional, Sequence

import numpy as np
import faiss
from fastembed import TextEmbedding

from app.utils.config import (
    EMBEDDING_MODEL,
    INDEX_DIR,
    RERANKER_MODEL,
    RETRIEVAL_CANDIDATES,
    RETRIEVAL_MODE,
)

FAISS_INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"
RRF_K = 60

_model = None
_index = None
_metadata = None
_bm25 = None
_reranker = None
_load_lock = threading.Lock()

_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how in is it its of on or that the this to was what "
    "when where which who why will with we you your i me my our they their there these those than then "
    "into about also has have had not but if so such".split()
)


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


class BM25:
    """Okapi BM25 over the passage texts (small corpus, so a plain in-memory implementation is enough)."""

    def __init__(self, documents: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_terms = [Counter(_tokenize(d)) for d in documents]
        self.doc_len = np.array([sum(c.values()) for c in self.doc_terms], dtype="float32")
        self.avg_len = float(self.doc_len.mean()) if len(documents) else 0.0
        df = Counter(term for terms in self.doc_terms for term in terms)
        n = len(documents)
        self.idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}
        self.postings: Dict[str, List[int]] = {}
        for i, terms in enumerate(self.doc_terms):
            for term in terms:
                self.postings.setdefault(term, []).append(i)

    def search(self, query: str, k: int) -> List[int]:
        scores: Dict[int, float] = {}
        for term in set(_tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i in self.postings[term]:
                tf = self.doc_terms[i][term]
                norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avg_len))
                scores[i] = scores.get(i, 0.0) + idf * norm
        return [i for i, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]]


def _lazy_load(mode: Optional[str] = None):
    with _load_lock:
        return _load(mode or RETRIEVAL_MODE)


def _load(mode: str):
    global _model, _index, _metadata, _bm25, _reranker
    if _index is None:
        if not FAISS_INDEX_PATH.exists():
            return False
        _index = faiss.read_index(str(FAISS_INDEX_PATH))
    if _metadata is None:
        if not METADATA_PATH.exists():
            return False
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _metadata = json.load(f)
    if mode != "bm25" and _model is None:
        # ONNX runtime model (no PyTorch): small enough for free hosting tiers
        _model = TextEmbedding(EMBEDDING_MODEL)
    if mode != "dense" and _bm25 is None:
        _bm25 = BM25([m["text"] for m in _metadata])
    if mode == "hybrid_rerank" and _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _reranker = TextCrossEncoder(RERANKER_MODEL)
    return True


def embed_query(question: str) -> np.ndarray:
    # query_embed adds the model's retrieval instruction prefix
    vector = np.array(list(_model.query_embed([question])), dtype="float32")
    faiss.normalize_L2(vector)
    return vector


def _dense_search(question: str, k: int) -> List[int]:
    _, indices = _index.search(embed_query(question), k)
    return [int(i) for i in indices[0] if i >= 0]


def _rrf(rankings: Sequence[Sequence[int]], k: int) -> List[int]:
    scores: Dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking):
            scores[i] = scores.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
    return [i for i, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]]


def search(question: str, top_k: int = 5, mode: Optional[str] = None) -> List[int]:
    """Return passage indices, best first."""
    mode = mode or RETRIEVAL_MODE
    if not _lazy_load(mode):
        return []

    if mode == "dense":
        return _dense_search(question, top_k)
    if mode == "bm25":
        return _bm25.search(question, top_k)

    candidates = _rrf(
        [_dense_search(question, RETRIEVAL_CANDIDATES), _bm25.search(question, RETRIEVAL_CANDIDATES)],
        RETRIEVAL_CANDIDATES,
    )
    if mode == "hybrid":
        return candidates[:top_k]

    # Small batches avoid padding every pair to the longest passage (~2x faster on CPU)
    scores = list(_reranker.rerank(question, [_metadata[i]["text"] for i in candidates], batch_size=4))
    order = np.argsort(scores)[::-1][:top_k]
    return [candidates[j] for j in order]


def retrieve_from_kb(question: str, top_k: int = 3) -> List[str]:
    """
    Retrieve top-k relevant chunks from the local knowledge base.
    Returns the chunk texts.
    """
    return [_metadata[i]["text"] for i in search(question, top_k)]
