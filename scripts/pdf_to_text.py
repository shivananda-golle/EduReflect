from pathlib import Path
import pdfplumber

# -------- Paths --------
PDF_DIR = Path("data/raw_pdfs")
OUT_DIR = Path("data/raw/textbooks")

OUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a single PDF file"""
    text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)

    return "\n".join(text)


def main():
    pdf_files = list(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print("❌ No PDF files found in data/raw_pdfs/")
        return

    print(f"📄 Found {len(pdf_files)} PDFs")

    for pdf_file in pdf_files:
        print(f"➡️ Processing {pdf_file.name}")

        text = extract_text_from_pdf(pdf_file)

        out_file = OUT_DIR / f"{pdf_file.stem}.txt"
        out_file.write_text(text, encoding="utf-8")

        print(f"✅ Saved {out_file}")

    print("\n🎉 PDF to text conversion completed")


if __name__ == "__main__":
    main()
