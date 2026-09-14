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


def build_prompt(question: str, documents: list[str], answer_format: str, depth: str, length: str, diagnostic: bool, document_context: str = ""):
    evidence_text = "\n\n".join(documents)[:MAX_EVIDENCE_CHARS]
    
    # If document context is provided, prioritize it over regular evidence
    if document_context:
        evidence_text = document_context[:MAX_EVIDENCE_CHARS]
    
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
        "Use only the provided evidence. If information is missing, say so briefly."
        "When answering questions about uploaded documents, provide direct answers without repeating the document content."
    )

    user_prompt = f"""
Question:
{question}

Evidence:
{evidence_text}

Instruction:
{format_instruction}
{depth_instruction}
{length_instruction}
{diag_instruction}
- Stay grounded in the evidence. If something is missing, say so briefly.
- Provide 2-3 suggested follow-up questions.
- Provide 3-6 key terms with one-line definitions (if present in evidence).
- If evidence is thin, include a one-line caveat at the end.
- IMPORTANT: Do not repeat or copy large portions of the document content in your answer.
"""

    return system_prompt, user_prompt


def generate_answer(question: str, documents: list[str], answer_format: str = "brief", depth: str = "standard", length: str = "medium", diagnostic: bool = False, document_context: str = ""):
    system_prompt, user_prompt = build_prompt(question, documents, answer_format, depth, length, diagnostic, document_context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        content = llm_client.chat(messages, max_tokens=480, temperature=0.3)

        # Simple heuristics for confidence/caveat; adjust as needed
        conf = "High" if len("\n\n".join(documents) + document_context) > 500 else "Medium"
        caveat = "Evidence was brief; consider a more specific question." if len("\n\n".join(documents) + document_context) < 300 else None
        
        # For now, leave terms/followups parsing to the UI or future structured prompts
        terms = []
        followups = []
        return content, conf, caveat, terms, followups
    except LimitExceeded:
        raise
    except Exception as e:
        raise RuntimeError(f"Generation failed: {e}")


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
