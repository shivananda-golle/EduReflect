import requests
from typing import List, Dict

from app.utils.config import HF_API_TOKEN, REFINER_MODEL, REQUEST_TIMEOUT, MAX_EVIDENCE_CHARS
from app.utils.evidence_utils import shorten_evidence

HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {HF_API_TOKEN}",
    "Content-Type": "application/json"
}

FILLER_KEYWORDS = [
    "hello", "hi", "hey", "today", "you know",
    "let's", "now", "cool", "right?", "so,"
]

ANALOGY_KEYWORDS = [
    "like a", "like an", "imagine", "magic",
    "superhero", "factory", "machine",
    "wave", "beach", "story"
]


def is_filler(sentence: str) -> bool:
    s = sentence.lower()
    return any(k in s for k in FILLER_KEYWORDS)


def is_analogy(sentence: str) -> bool:
    s = sentence.lower()
    return any(k in s for k in ANALOGY_KEYWORDS)


def refine_sentence(sentence: str, evidence: str) -> str:
    """
    Rewrite ONE sentence to be factually correct using evidence.
    """
    system_prompt = (
        "You rewrite ONE sentence to be factually correct.\n"
        "Rules:\n"
        "- Output exactly ONE sentence.\n"
        "- Use simple textbook language.\n"
        "- Do NOT add examples or analogies.\n"
        "- Do NOT mention evidence.\n"
        "- Do NOT add new facts.\n"
    )

    user_prompt = f"""
Sentence:
{sentence}

Evidence:
{evidence}

Instruction:
Rewrite the sentence so it is accurate and clear.
"""

    payload = {
        "model": REFINER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 80,
        "temperature": 0.0
    }

    response = requests.post(HF_CHAT_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    output = response.json()["choices"][0]["message"]["content"].strip()
    return output.split("\n")[0]


def refine_answer(
    verified_claims: List[Dict],
    evidence_docs: List[str]
) -> str:
    """
    Sentence type                  → Action
    ------------------------------------------------
    Filler / greeting              → DROP
    Analogy                        → DROP
    SUPPORTED                      → KEEP
    CONTRADICTED                   → REFINE
    NOT_ENOUGH_INFO                → REFINE
    """
    evidence = shorten_evidence(evidence_docs, max_chars=min(MAX_EVIDENCE_CHARS, 800))

    final_sentences = []
    seen = set()

    for claim in verified_claims:
        sentence = claim["sentence"].strip()
        verdict = claim["verdict"]

        if len(sentence) < 8:
            continue
        if is_filler(sentence):
            continue
        if is_analogy(sentence):
            continue

        if verdict == "SUPPORTED":
            cleaned = sentence
        elif verdict in ("CONTRADICTED", "NOT_ENOUGH_INFO"):
            cleaned = refine_sentence(sentence, evidence)
        else:
            continue

        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            final_sentences.append(cleaned)

    if final_sentences:
        return " ".join(final_sentences)

    # Fallback: concise, neutral response
    return "I could not confidently answer this question with the available evidence."