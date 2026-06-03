"""Natural-language queries over the event history.

BM25-retrieve the most relevant events for the question (if rank-bm25 is
installed), then ask the LLM to answer using them. With no model, returns the
retrieved events directly so the command is still useful.
"""

from __future__ import annotations

from collections.abc import Sequence

from spero.ai.llm import LLMClient

_SYSTEM = "Answer the operator's question using only the supervision events provided. Be concise."


def rank_events(question: str, docs: Sequence[str], k: int) -> list[str]:
    """Return the top-k docs most relevant to the question (BM25 if available)."""
    if not docs:
        return []
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return list(docs)[-k:]  # no ranker: fall back to most recent
    tokenized = [d.lower().split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(question.lower().split())
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    return [docs[i] for i in ranked[:k]]


async def nl_query(question: str, docs: Sequence[str], llm: LLMClient, *, k: int = 10) -> str:
    top = rank_events(question, docs, k)
    if not top:
        return "No events recorded yet."
    prompt = f"Question: {question}\n\nRelevant events:\n" + "\n".join(f"- {d}" for d in top)
    answer = await llm.complete(prompt, system=_SYSTEM)
    if answer:
        return answer
    return "No model configured. Most relevant events:\n" + "\n".join(f"- {d}" for d in top)
