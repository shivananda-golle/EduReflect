import re
from pathlib import Path

# -------- Paths --------
RAW_TEXT_DIR = Path("data/raw")
CLEAN_TEXT_DIR = Path("data/clean")

CLEAN_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(text: str) -> str:
    # Remove page numbers
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)

    # Remove excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove multiple spaces
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Remove citation markers like [1], [12]
    text = re.sub(r"\[\d+\]", "", text)

    # Strip leading/trailing spaces
    return text.strip()


def main():
    txt_files = list(RAW_TEXT_DIR.rglob("*.txt"))

    if not txt_files:
        print("❌ No .txt files found in data/raw/")
        return

    print(f"🧹 Found {len(txt_files)} text files to clean")

    for txt_file in txt_files:
        print(f"➡️ Cleaning {txt_file}")

        raw_text = txt_file.read_text(encoding="utf-8", errors="ignore")
        cleaned = clean_text(raw_text)

        out_path = CLEAN_TEXT_DIR / txt_file.relative_to(RAW_TEXT_DIR)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cleaned, encoding="utf-8")

        print(f"✅ Saved cleaned file to {out_path}")

    print("\n🎉 Text cleaning completed")


if __name__ == "__main__":
    main()
