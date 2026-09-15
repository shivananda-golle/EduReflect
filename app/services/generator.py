import json

from app.services import llm_client
from app.services.usage_limits import LimitExceeded
from app.utils.config import MAX_EVIDENCE_CHARS

FORMAT_INSTRUCTIONS = {
    "brief": "Write a concise paragraph in plain language. Add 1–2 short, concrete examples if helpful.",
    "bullets": "Write 4–7 bullet points. Each bullet should be short and factual. Include an example bullet if relevant.",
    "presentation": "Write a presentation-ready mini-script with 3–5 short sections. Use headings and 1–2 sentences under each heading. Keep it tight and confident; no fluff.",
}

DEPTH_INSTRUCTIONS = {
    "kid": "Use simple language a 10-year-old can follow.",
    "standard": "Use clear, student-friendly language.",
    "exam": "Be concise and exam-focused.",
}

LENGTH_INSTRUCTIONS = {
    "short": "Keep it very concise (4–6 sentences or ~80–120 words).",
    "medium": "Keep it ~8–12 sentences or ~150–220 words.",
    "long": "Allow a fuller explanation (~12–18 sentences or ~250–350 words).",
}


MAX_TOKENS = {"short": 600, "medium": 800, "long": 1100}

CONFIDENCE = {"full": "High", "partial": "Medium", "none": "Low"}


def pack_evidence(documents: list[str], max_chars: int = MAX_EVIDENCE_CHARS) -> str:
    """Number whole passages ([1], [2], ...) until the character budget is reached, never cutting one mid-way."""
    parts = []
    used = 0
    for i, doc in enumerate(documents, 1):
        block = f"[{i}] {doc.strip()}"
        if parts and used + len(block) > max_chars:
            break
        parts.append(block[:max_chars])
        used += len(block) + 2
    return "\n\n".join(parts)


def build_prompt(question: str, documents: list[str], answer_format: str, depth: str, length: str, diagnostic: bool, document_context: str = ""):
    # Raw document text (legacy callers) is packed like passages; routes pass selected passages as documents
    evidence_text = pack_evidence([document_context] if document_context else documents)

    format_instruction = FORMAT_INSTRUCTIONS.get(answer_format, FORMAT_INSTRUCTIONS["brief"])
    depth_instruction = DEPTH_INSTRUCTIONS.get(depth, DEPTH_INSTRUCTIONS["standard"])
    length_instruction = LENGTH_INSTRUCTIONS.get(length, LENGTH_INSTRUCTIONS["medium"])

    diag_instruction = ""
    if diagnostic:
        diag_instruction = (
            "- Before the main answer, provide 2–3 very short diagnostic questions to gauge prior knowledge. "
            "Keep each diagnostic question on its own line prefixed with 'Q:'. "
        )

    system_prompt = (
        "You are an educational assistant helping students learn new concepts. "
        "Use only the provided evidence. If information is missing, say so briefly. "
        "When answering questions about uploaded documents, provide direct answers without repeating the document content."
    )

    user_prompt = f"""
Question:
{question}

Evidence (numbered passages):
{evidence_text}

Instruction:
{format_instruction}
{depth_instruction}
{length_instruction}
{diag_instruction}
- Stay grounded in the evidence. Ignore passages that are not relevant to the question.
- End every sentence that states a fact from the evidence with the number of its passage in square brackets, e.g. [1] or [2][3].
- If the evidence does not cover part of the question, say so briefly instead of guessing.
- Write formulas in plain text or Unicode (for example: area = √(s(s−a)(s−b)(s−c)), s = (a+b+c)/2, x²). Never use LaTeX or backslashes.
- IMPORTANT: Do not repeat or copy large portions of the evidence in your answer.

Return a JSON object with exactly these four keys, in this order:
- "coverage": exactly one of "full" (the evidence answers the question), "partial" (only in part), or "none" (the evidence does not address it)
- "answer": the answer as Markdown (formatted as instructed above; no follow-ups or key terms inside it)
- "key_terms": 3-6 objects {{"term": "...", "definition": "one line"}} taken from the evidence ([] if none)
- "followups": 2-3 short follow-up questions about the topic that the evidence could help answer
"""

    return system_prompt, user_prompt


def generate_answer(question: str, documents: list[str], answer_format: str = "brief", depth: str = "standard", length: str = "medium", diagnostic: bool = False, document_context: str = ""):
    system_prompt, user_prompt = build_prompt(question, documents, answer_format, depth, length, diagnostic, document_context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        content = llm_client.chat(
            messages,
            max_tokens=MAX_TOKENS.get(length, MAX_TOKENS["medium"]),
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except LimitExceeded:
        raise
    except Exception as e:
        raise RuntimeError(f"Generation failed: {e}")

    return parse_answer(content)


def parse_answer(content: str):
    """Turn the model's JSON into (answer, confidence, caveat, terms, followups); fall back to raw text."""
    try:
        data = json.loads(content)
        answer = str(data.get("answer") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        return content, None, None, [], []
    if not answer:
        return content, None, None, [], []

    terms = [
        f"{t['term']}: {t['definition']}"
        for t in data.get("key_terms") or []
        if isinstance(t, dict) and t.get("term") and t.get("definition")
    ]
    if terms:
        answer += "\n\n**Key terms**\n" + "\n".join(f"- **{t.split(': ', 1)[0]}**: {t.split(': ', 1)[1]}" for t in terms)

    followups = [str(f).strip() for f in data.get("followups") or [] if str(f).strip()][:3]
    coverage = str(data.get("coverage", "")).lower()
    conf = CONFIDENCE.get(coverage)
    caveat = {
        "partial": "The knowledge base only partly covers this question, so parts of the answer may be incomplete.",
        "none": "The knowledge base doesn't cover this question well. Try rephrasing or asking about a related topic.",
    }.get(coverage)
    return answer, conf, caveat, terms, followups


def optimize_prompt(raw_question: str) -> str:
    """
    Rewrite user's question into a clear, model-friendly prompt.
    Keeps intent, removes fluff, adds missing specificity, and fixes grammar.
    Output: a single concise prompt string.
    """
    system_prompt = (
        "You are a prompt engineer for an educational QA system.\n"
        "Rewrite the user's question into a clear, specific, model-ready prompt.\n"
        "Rules:\n"
        "- Preserve the original intent.\n"
        "- Remove greetings, filler, and slang.\n"
        "- Resolve pronouns and ambiguity (name the subject).\n"
        "- Include key entities, constraints, or examples if implied.\n"
        "- Ask ONE question in plain language.\n"
        "- Output ONLY the rewritten prompt without extra text."
    )
    user_prompt = f"User question:\n{raw_question}\n\nRewritten prompt:"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    try:
        return llm_client.chat(messages, max_tokens=120, temperature=0.0) or raw_question.strip()
    except Exception:
        # Rewriting is optional: fall back to the original question on any failure, including limits
        return raw_question.strip()
