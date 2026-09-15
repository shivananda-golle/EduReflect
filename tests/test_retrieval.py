"""Regression guard for retrieval quality on the evaluation set (see eval/evaluate_retrieval.py)."""
from eval.evaluate_retrieval import QUESTIONS, evaluate
import json


def test_hybrid_retrieval_quality():
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    result = evaluate("hybrid", questions)
    # Measured at 82.7% hit@1 / 97.3% hit@5; allow a small margin for model/runtime differences
    assert result["hit@5"] >= 0.93
    assert result["hit@1"] >= 0.78
