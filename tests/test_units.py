import json

from app.services.document_processor import sample_for_summary, select_relevant_passages
from app.services.generator import pack_evidence, parse_answer
from app.services.kb_retriever import BM25
from app.services.question_generator import _loads_lenient, validate_questions


def test_pack_evidence_keeps_whole_numbered_passages():
    docs = ["a" * 1000, "b" * 1000, "c" * 1000]
    packed = pack_evidence(docs, max_chars=2100)
    assert packed.startswith("[1] ") and "[2] " in packed and "[3]" not in packed
    assert packed.count("b") == 1000  # never cut mid-passage


def test_parse_answer_structured_and_fallback():
    content = json.dumps({
        "answer": "Text [1].",
        "key_terms": [{"term": "Force", "definition": "A push or pull"}],
        "followups": ["Q1?", "Q2?", "Q3?", "Q4?"],
        "coverage": "partial",
    })
    answer, conf, caveat, terms, followups = parse_answer(content)
    assert answer.startswith("Text [1].") and "**Force**: A push or pull" in answer
    assert conf == "Medium" and caveat and terms == ["Force: A push or pull"] and len(followups) == 3
    assert parse_answer("plain text") == ("plain text", None, None, [], [])


def test_lenient_json_handles_latex_backslashes():
    parsed = _loads_lenient(r'{"questions": [{"options": ["\sqrt{2}", "\frac{1}{2}"]}]}')
    assert parsed["questions"][0]["options"] == [r"\sqrt{2}", r"\frac{1}{2}"]


def test_validate_questions_drops_malformed():
    questions = [
        {"question": "Good?", "options": ["x", "y", "z", "w"], "correct_answer": "x"},
        {"question": "Answer not an option?", "options": ["x", "y"], "correct_answer": "q"},
        {"question": "Good?", "options": ["x", "y"], "correct_answer": "x"},  # duplicate
        {"question": "", "options": ["x", "y"], "correct_answer": "x"},
    ]
    assert [q["question"] for q in validate_questions(questions)] == ["Good?"]


def test_bm25_ranks_keyword_match_first():
    bm25 = BM25(["the cat sat on the mat", "Heron's formula gives the area of a triangle", "photosynthesis in plants"])
    assert bm25.search("area of a triangle with Heron's formula", 3)[0] == 1


def test_document_passage_selection_finds_relevant_part_of_long_text():
    filler = " ".join(f"word{i}" for i in range(3000))
    text = filler + " The mitochondria is the powerhouse of the cell. " + filler
    selected = select_relevant_passages(text, "What is the powerhouse of the cell?", max_chars=2000)
    assert any("powerhouse" in p for p in selected)
    assert sum(len(p) for p in selected) <= 2000


def test_summary_sample_spans_whole_document():
    text = " ".join(f"w{i}" for i in range(20000))
    sample = sample_for_summary(text, max_chars=3000)
    indices = [int(token[1:]) for token in sample.split()]
    assert len(sample) <= 3500
    assert min(indices) == 0 and max(indices) > 15000  # beginning and late parts of the document
