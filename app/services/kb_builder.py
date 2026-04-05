import json
from pathlib import Path
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

CLEAN_DATA_DIR = Path("data/clean")
INDEX_DIR = Path("data/index")

INDEX_DIR.mkdir(parents=True, exist_ok=True)

FAISS_INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "metadata.json"

model = SentenceTransformer("intfloat/e5-base")


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


def main():
    passages = []
    metadata = []

    txt_files = list(CLEAN_DATA_DIR.rglob("*.txt"))
    if not txt_files:
        print("❌ No cleaned text files found in data/clean/")
        return

    print(f"📚 Found {len(txt_files)} cleaned text files")

    for file in txt_files:
        print(f"➡️ Processing {file}")
        text = file.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text)

        for chunk in chunks:
            passages.append("passage: " + chunk)
            metadata.append({
                "source": str(file),
                "chunk_id": len(metadata),
                "text": chunk
            })

    if not passages:
        print("❌ No passages created after filtering.")
        return

    print(f"🔢 Total chunks created: {len(passages)}")

    embeddings = model.encode(passages, normalize_embeddings=True, show_progress_bar=True)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(np.array(embeddings))

    faiss.write_index(index, str(FAISS_INDEX_PATH))

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\n✅ Knowledge base built successfully")
    print(f"📁 FAISS index saved to: {FAISS_INDEX_PATH}")
    print(f"📁 Metadata saved to: {METADATA_PATH}")


if __name__ == "__main__":
    main()