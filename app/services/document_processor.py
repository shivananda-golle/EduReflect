import json
from typing import Any, Dict, List

import PyPDF2
from docx import Document

from app.services import llm_client
from app.services.generator import generate_answer
from app.services.kb_retriever import BM25
from app.services.usage_limits import LimitExceeded
from app.utils.config import MAX_EVIDENCE_CHARS

PASSAGE_WORDS = 150
SUMMARY_CONTEXT_CHARS = 6000


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF file"""
    with open(file_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        # Scanned pages have no text layer and return None
        return "\n".join(page.extract_text() or "" for page in pdf_reader.pages)


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX file"""
    doc = Document(file_path)
    return "\n".join(paragraph.text for paragraph in doc.paragraphs)


def split_passages(text: str, words_per_passage: int = PASSAGE_WORDS) -> List[str]:
    words = text.split()
    return [" ".join(words[i:i + words_per_passage]) for i in range(0, len(words), words_per_passage)]


def select_relevant_passages(text: str, question: str, max_chars: int = MAX_EVIDENCE_CHARS) -> List[str]:
    """Pick the passages of a document most relevant to the question (BM25), in document order, within the budget."""
    passages = split_passages(text)
    if sum(len(p) for p in passages) <= max_chars:
        return passages

    ranked = BM25(passages).search(question, len(passages)) or list(range(len(passages)))
    chosen, used = [], 0
    for i in ranked:
        if used + len(passages[i]) > max_chars:
            break
        chosen.append(i)
        used += len(passages[i])
    return [passages[i] for i in sorted(chosen)] or passages[:1]


def sample_for_summary(text: str, max_chars: int = SUMMARY_CONTEXT_CHARS) -> str:
    """Evenly spaced passages from the whole document, so long files are summarised beyond their first pages."""
    passages = split_passages(text)
    if sum(len(p) for p in passages) <= max_chars:
        return "\n\n".join(passages)
    per_passage = max(1, len(" ".join(passages)) // len(passages))
    count = max(1, max_chars // (per_passage + 2))
    if count == 1:
        return passages[0]
    # Spread from the first passage to the last one inclusive
    picks = sorted({round(k * (len(passages) - 1) / (count - 1)) for k in range(count)})
    return "\n\n".join(passages[i] for i in picks)


def summarize_document(text: str) -> str:
    messages = [
        {"role": "system", "content": "You summarise study documents for students."},
        {
            "role": "user",
            "content": (
                "Summarise this document in 2-3 sentences: what it is and its main topics. "
                "The excerpts are sampled from across the whole document.\n\n"
                f"{sample_for_summary(text)}\n\n"
                'Return JSON: {"summary": "..."}'
            ),
        },
    ]
    content = llm_client.chat(messages, max_tokens=400, temperature=0.2, response_format={"type": "json_object"})
    return str(json.loads(content).get("summary", "")).strip()


def process_document(file_path: str, question: str = "") -> Dict[str, Any]:
    """Process uploaded document and optionally answer questions about it"""

    # Extract text based on file type
    if file_path.lower().endswith('.pdf'):
        full_text = extract_text_from_pdf(file_path)
    elif file_path.lower().endswith('.docx'):
        full_text = extract_text_from_docx(file_path)
    else:
        raise ValueError("Unsupported file type")

    if not full_text.strip():
        return {
            "summary": "No text could be extracted. The file may be a scanned image without a text layer.",
            "full_text": "",
            "answer": "Unable to answer: the document has no extractable text." if question else None,
        }

    try:
        summary = summarize_document(full_text)
    except LimitExceeded:
        raise
    except Exception:
        summary = f"Document processed successfully. Length: {len(full_text)} characters."

    result = {"summary": summary, "full_text": full_text}

    # If question is provided, answer it from the most relevant parts of the document
    if question:
        try:
            answer = generate_answer(question, select_relevant_passages(full_text, question), answer_format="brief")[0]
            result["answer"] = answer
        except LimitExceeded:
            raise
        except Exception:
            result["answer"] = "Unable to generate answer from document."

    return result
