from typing import List

def shorten_evidence(docs: List[str], max_chars: int = 2000) -> str:
    out = []
    total = 0
    for d in docs:
        if total + len(d) > max_chars:
            break
        out.append(d)
        total += len(d)
    return "\n\n".join(out)