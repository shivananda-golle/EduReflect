import requests
import nltk
from typing import List, Dict

from app.utils.config import HF_API_TOKEN, VERIFIER_MODEL, MAX_EVIDENCE_CHARS, REQUEST_TIMEOUT
from app.utils.evidence_utils import shorten_evidence

# Ensure tokenizer is present (guarded)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

HF_VERIFIER_URL = f"https://router.huggingface.co/hf-inference/models/{VERIFIER_MODEL}"

HEADERS = {
    "Authorization": f"Bearer {HF_API_TOKEN}",
    "Content-Type": "application/json"
}

PEDAGOGY_PREFIXES = (
    "hey", "hello", "imagine", "think of",
    "let's", "now,", "so,", "guess what"
)


def is_pedagogical(sentence: str) -> bool:
    return sentence.lower().startswith(PEDAGOGY_PREFIXES)


def split_into_sentences(text: str) -> List[str]:
    text = text.replace("\n", " ")
    sentences = nltk.sent_tokenize(text)
    return [s.strip() for s in sentences if len(s.strip()) > 6]


def verify_sentence(sentence: str, evidence: str) -> Dict:
    evidence = evidence[:MAX_EVIDENCE_CHARS]

    payload = {"inputs": f"{evidence} </s></s> {sentence}"}

    response = requests.post(HF_VERIFIER_URL, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    results = response.json()[0]
    top = max(results, key=lambda x: x["score"])

    label = top["label"]
    score = top["score"]

    if label == "ENTAILMENT" and score >= 0.7:
        verdict = "SUPPORTED"
    elif label == "CONTRADICTION" and score >= 0.7:
        verdict = "CONTRADICTED"
    else:
        verdict = "NOT_ENOUGH_INFO"

    return {
        "sentence": sentence,
        "verdict": verdict,
        "score": round(score, 3)
    }


def verify_answer(answer: str, evidence_docs: List[str]) -> List[Dict]:
    combined_evidence = shorten_evidence(evidence_docs, max_chars=MAX_EVIDENCE_CHARS)
    sentences = split_into_sentences(answer)[:8]

    verified_claims = []

    for sentence in sentences:
        if is_pedagogical(sentence):
            verified_claims.append({
                "sentence": sentence,
                "verdict": "SUPPORTED",
                "score": 1.0
            })
            continue

        claim = verify_sentence(sentence, combined_evidence)
        verified_claims.append(claim)

    return verified_claims