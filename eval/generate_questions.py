"""
Generate a synthetic retrieval evaluation set from the knowledge base.

For a fixed random sample of passages, the LLM writes one realistic student question that the
passage answers. evaluate_retrieval.py then checks whether retrieval ranks that passage highly.

    python -m eval.generate_questions --n 80
"""
import argparse
import json
import random
import re
import time

from app.services import llm_client
from app.services.usage_limits import LimitExceeded
from app.utils.config import INDEX_DIR, PROJECT_ROOT

OUTPUT = PROJECT_ROOT / "eval" / "retrieval_questions.json"
BATCH = 5

PROMPT = """For each numbered passage from a school science/maths knowledge base, write ONE question a
student might ask that this specific passage answers well.

Rules:
- Paraphrase like a student would; do not copy distinctive phrases or long spans from the passage.
- The question must be answerable from the passage alone and be specific to its content.
- If a passage is too noisy or generic to support a clear question, use null.

Return JSON: {{"questions": [{{"id": <passage number>, "question": "<text or null>"}}, ...]}}

{passages}"""


def is_usable(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    return len(text) > 300 and letters / len(text) > 0.7


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=80)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    metadata = json.loads((INDEX_DIR / "metadata.json").read_text(encoding="utf-8"))
    candidates = [i for i, m in enumerate(metadata) if is_usable(m["text"])]
    sample = random.Random(args.seed).sample(candidates, args.n)

    items = []
    for start in range(0, len(sample), BATCH):
        batch = sample[start:start + BATCH]
        passages = "\n\n".join(f"[{k + 1}] {metadata[i]['text']}" for k, i in enumerate(batch))
        for attempt in range(5):
            try:
                content = llm_client.chat(
                    [{"role": "user", "content": PROMPT.format(passages=passages)}],
                    max_tokens=800,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                break
            except LimitExceeded:
                # Free-tier tokens-per-minute limit: wait for the window to reset
                time.sleep(30)
        else:
            raise RuntimeError("LLM stayed rate-limited")
        for q in json.loads(content).get("questions", []):
            k = int(q.get("id", 0)) - 1
            text = (q.get("question") or "").strip()
            if 0 <= k < len(batch) and text:
                i = batch[k]
                items.append({"question": text, "chunk_id": i, "source": re.sub(r".*/", "", metadata[i]["source"])})
        print(f"{min(start + BATCH, len(sample))}/{len(sample)} passages processed, {len(items)} questions")

    OUTPUT.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(items)} questions to {OUTPUT}")


if __name__ == "__main__":
    main()
