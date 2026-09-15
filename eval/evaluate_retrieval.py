"""
Measure retrieval quality on eval/retrieval_questions.json.

    python -m eval.evaluate_retrieval                       # all modes
    python -m eval.evaluate_retrieval --modes dense hybrid

Metrics per mode:
- hit@k: the passage the question was written from is in the top k
- MRR@10: mean reciprocal rank of that passage
- src@5: any passage from the same source document is in the top 5
- ms/q: average search latency (after models are loaded)
"""
import argparse
import json
import time

from app.services import kb_retriever
from app.utils.config import PROJECT_ROOT

QUESTIONS = PROJECT_ROOT / "eval" / "retrieval_questions.json"


def evaluate(mode: str, questions):
    kb_retriever._lazy_load(mode)
    kb_retriever.search(questions[0]["question"], 10, mode)  # warm-up

    hits = {1: 0, 3: 0, 5: 0}
    rr = 0.0
    src5 = 0
    elapsed = 0.0
    for q in questions:
        start = time.perf_counter()
        ranked = kb_retriever.search(q["question"], 10, mode)
        elapsed += time.perf_counter() - start

        if q["chunk_id"] in ranked:
            rank = ranked.index(q["chunk_id"]) + 1
            rr += 1 / rank
            for k in hits:
                hits[k] += rank <= k
        sources = [kb_retriever._metadata[i]["source"].rsplit("/", 1)[-1] for i in ranked[:5]]
        src5 += q["source"] in sources

    n = len(questions)
    return {
        "hit@1": hits[1] / n,
        "hit@3": hits[3] / n,
        "hit@5": hits[5] / n,
        "MRR@10": rr / n,
        "src@5": src5 / n,
        "ms/q": 1000 * elapsed / n,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", default=["dense", "bm25", "hybrid", "hybrid_rerank"])
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    print(f"{len(questions)} questions\n")
    print(f"{'mode':16s} {'hit@1':>6s} {'hit@3':>6s} {'hit@5':>6s} {'MRR@10':>7s} {'src@5':>6s} {'ms/q':>7s}")
    for mode in args.modes:
        r = evaluate(mode, questions)
        print(f"{mode:16s} {r['hit@1']:6.1%} {r['hit@3']:6.1%} {r['hit@5']:6.1%} {r['MRR@10']:7.3f} {r['src@5']:6.1%} {r['ms/q']:7.1f}")


if __name__ == "__main__":
    main()
