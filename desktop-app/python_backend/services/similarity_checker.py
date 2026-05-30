"""
Semantic Similarity Checker

Used to detect whether a new interviewer question is topically related
to the current active question (→ FOLLOWUP) or completely different (→ OVERRIDE).

Strategy:
  1. Keyword overlap heuristic (zero latency, no network).
  2. Optional LLM-based check if heuristic is inconclusive.

The heuristic is intentionally conservative:
  - Unrelated → trigger override (false positives are safer than missing overrides)
"""

from __future__ import annotations

import re
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Stop words to ignore in keyword overlap
_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "on", "at", "by",
    "for", "with", "about", "against", "between", "into", "through",
    "and", "but", "or", "so", "yet", "not", "no", "yes", "you", "your",
    "me", "my", "we", "our", "it", "its", "this", "that", "what", "how",
    "why", "when", "where", "who", "which", "tell", "explain", "describe",
    "can", "could", "would", "please",
}

# Minimum Jaccard similarity to consider questions related
RELATED_THRESHOLD = 0.15


def _tokenise(text: str) -> set[str]:
    """Lower-case alphabetic tokens, remove stop words."""
    tokens = re.findall(r"[a-z]+", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS and len(t) > 2}


def jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two strings."""
    set_a = _tokenise(a)
    set_b = _tokenise(b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def is_related_heuristic(new_question: str, current_question: str) -> bool:
    """
    Returns True if the new question appears topically related to the current one.
    Uses Jaccard keyword overlap.
    """
    sim = jaccard_similarity(new_question, current_question)
    logger.debug(
        "Jaccard similarity: %.3f  |  current='%s...'  new='%s...'",
        sim,
        current_question[:60],
        new_question[:60],
    )
    return sim >= RELATED_THRESHOLD


async def is_related_llm(
    new_question: str,
    current_question: str,
    llm_client,
    deployment: str,
) -> bool:
    """
    LLM-based semantic relatedness check.
    Returns True if the new question is related to the current question.
    Runs in a thread pool executor (non-blocking).
    """
    prompt = f"""Are these two interview questions about the same topic?

Question A: "{current_question}"
Question B: "{new_question}"

Answer with ONLY "yes" or "no"."""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: llm_client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=5,
            ),
        )
        answer = response.choices[0].message.content.strip().lower()
        return "yes" in answer
    except Exception as exc:
        logger.warning("LLM similarity check failed, falling back to heuristic: %s", exc)
        return is_related_heuristic(new_question, current_question)


async def check_similarity(
    new_question: str,
    current_question: Optional[str],
    llm_client=None,
    deployment: str = "",
    use_llm: bool = False,
) -> bool:
    """
    High-level entry point.

    Returns True  → questions are related (no override needed)
    Returns False → questions are unrelated (trigger OVERRIDE)
    """
    if not current_question:
        # No active question — nothing to compare against
        return False

    heuristic_result = is_related_heuristic(new_question, current_question)

    # If heuristic gives a confident result (very high or very low similarity),
    # skip the LLM call to save latency.
    sim = jaccard_similarity(new_question, current_question)
    confident = sim > 0.30 or sim < 0.05

    if confident or not use_llm or llm_client is None:
        return heuristic_result

    # Inconclusive range — escalate to LLM
    return await is_related_llm(new_question, current_question, llm_client, deployment)
