"""
Build the FAISS index used by kb_retriever.

    python -m app.services.kb_builder                   # chunk data/clean/**/*.txt and embed
    python -m app.services.kb_builder --from-metadata   # re-embed passages already in metadata.json
                                                        # (use after changing EMBEDDING_MODEL)
"""
import argparse
import json

import numpy as np
import faiss
from fastembed import TextEmbedding

from app.utils.config import EMBEDDING_MODEL, INDEX_DIR, PROJECT_ROOT

CLEAN_DATA_DIR = PROJECT_ROOT / "data" / "clean"
FAISS_INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"


def chunk_text(text: str, chunk_size: int = 120):
    """
    Split text into clean chunks; skip tiny/noisy chunks.
    """
    words = text.split()
    chunks = []

    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk = " ".join(chunk_words)

        if len(chunk.strip()) < 60:
            continue

        symbol_ratio = sum(1 for c in chunk if not c.isalnum() and c != " ") / max(len(chunk), 1)
        if symbol_ratio > 0.15:
            continue

        chunks.append(chunk)

    return chunks


def load_clean_passages():
    metadata = []

    txt_files = sorted(CLEAN_DATA_DIR.rglob("*.txt"))
    if not txt_files:
        print("❌ No cleaned text files found in data/clean/")
        return metadata

    print(f"📚 Found {len(txt_files)} cleaned text files")

    for file in txt_files:
        print(f"➡️ Processing {file}")
        text = file.read_text(encoding="utf-8", errors="ignore")
        for chunk in chunk_text(text):
            metadata.append({
                "source": file.relative_to(PROJECT_ROOT).as_posix(),
                "chunk_id": len(metadata),
                "text": chunk
            })

    return metadata


def load_existing_passages():
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    for item in metadata:
        item["source"] = item["source"].replace("\\", "/")
    print(f"📚 Loaded {len(metadata)} passages from {METADATA_PATH}")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-metadata", action="store_true", help="re-embed passages from the existing metadata.json")
    args = parser.parse_args()

    metadata = load_existing_passages() if args.from_metadata else load_clean_passages()
    if not metadata:
        print("❌ No passages to index.")
        return

    print(f"🔢 Embedding {len(metadata)} passages with {EMBEDDING_MODEL}")
    model = TextEmbedding(EMBEDDING_MODEL)
    embeddings = np.array(list(model.passage_embed([m["text"] for m in metadata], batch_size=64)), dtype="float32")
    faiss.normalize_L2(embeddings)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print("\n✅ Knowledge base built successfully")
    print(f"📁 FAISS index saved to: {FAISS_INDEX_PATH}")
    print(f"📁 Metadata saved to: {METADATA_PATH}")


if __name__ == "__main__":
    main()
