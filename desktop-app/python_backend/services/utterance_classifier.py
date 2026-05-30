"""
Utterance Classifier

Classifies each interviewer utterance into one of:
  NEW_QUESTION   — a fresh, standalone question
  FOLLOWUP       — a question about the same topic
  HINT           — a guiding statement ("think about X", "consider Y")
  CLARIFICATION  — asking the candidate to elaborate/repeat

Strategy:
  1. Fast heuristic rules (no network call, zero latency).
  2. If confidence is low AND an LLM client is available,
     optionally fall back to GPT-4.1 for disambiguation.
     (LLM fallback is async and fire-and-forget to stay non-blocking.)
"""

from __future__ import annotations

import re
import asyncio
import logging
from typing import Optional

from models.live_schemas import UtteranceType

logger = logging.getLogger(__name__)


# ── Heuristic patterns ────────────────────────────────────────────────────────

# Hint phrases: interviewer is guiding, NOT asking a new question
_HINT_PATTERNS = re.compile(
    r"\b(think about|consider|remember that|keep in mind|"
    r"don't forget|what about|how about|have you thought|"
    r"hint:|clue:|try to|perhaps|maybe think)\b",
    re.IGNORECASE,
)

# Clarification patterns: asking candidate to elaborate / repeat
_CLARIFICATION_PATTERNS = re.compile(
    r"\b(can you (explain|elaborate|clarify|repeat|expand)|"
    r"what do you mean|could you clarify|tell me more|"
    r"please (elaborate|explain|clarify)|"
    r"i (didn't|don't) (understand|follow)|say that again)\b",
    re.IGNORECASE,
)

# Question words that strongly suggest a NEW question
_QUESTION_STARTERS = re.compile(
    r"^(what|how|why|when|where|who|which|describe|explain|"
    r"tell me|can you|could you|walk me through|have you|"
    r"do you|did you|would you|is there|are there)\b",
    re.IGNORECASE,
)

# Follow-up indicators: question that references the previous answer
_FOLLOWUP_INDICATORS = re.compile(
    r"\b(so|and|but|also|also|going back|related to that|"
    r"building on|following up|based on what you said|"
    r"you mentioned|earlier you said|with that in mind)\b",
    re.IGNORECASE,
)

SHORT_HINT_WORD_LIMIT = 15   # hints are typically short


def classify_interviewer_utterance(
    text: str,
    previous_question: Optional[str] = None,
) -> UtteranceType:
    """
    Classify an interviewer utterance using heuristic rules.

    Parameters
    ----------
    text : str
        The interviewer's utterance text.
    previous_question : Optional[str]
        The last question asked (for context).

    Returns
    -------
    UtteranceType
    """
    text_stripped = text.strip()
    word_count = len(text_stripped.split())

    # ── Rule 1: Hint detection ────────────────────────────────────────────────
    if _HINT_PATTERNS.search(text_stripped):
        # Hints are usually short; long sentences with hint words might still be questions
        if word_count <= SHORT_HINT_WORD_LIMIT or not _QUESTION_STARTERS.match(text_stripped):
            return UtteranceType.HINT

    # ── Rule 2: Clarification detection ──────────────────────────────────────
    if _CLARIFICATION_PATTERNS.search(text_stripped):
        return UtteranceType.CLARIFICATION

    # ── Rule 3: Must have a question mark or question starter to be a question ─
    has_question_mark = "?" in text_stripped
    has_question_starter = bool(_QUESTION_STARTERS.match(text_stripped))

    if not has_question_mark and not has_question_starter:
        # Not a question — treat as hint/comment
        return UtteranceType.HINT

    # ── Rule 4: Follow-up vs new question ────────────────────────────────────
    has_followup_indicator = bool(_FOLLOWUP_INDICATORS.search(text_stripped))

    if has_followup_indicator and previous_question:
        return UtteranceType.FOLLOWUP

    # Default: it's a new question
    return UtteranceType.NEW_QUESTION


async def classify_with_llm_fallback(
    text: str,
    previous_question: Optional[str],
    llm_client,           # AzureOpenAI client (passed in, not imported, to avoid circular deps)
    deployment: str,
) -> UtteranceType:
    """
    LLM-assisted classification — only called when heuristic confidence is low.
    Non-blocking: runs in a thread pool so it doesn't stall the event loop.
    """
    prompt = f"""Classify the following interviewer utterance into exactly one category.
Categories: NEW_QUESTION, FOLLOWUP, HINT, CLARIFICATION

Previous question: {previous_question or "(none)"}
Current utterance: "{text}"

Return ONLY the category name, nothing else."""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: llm_client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=10,
            ),
        )
        label = response.choices[0].message.content.strip().upper()
        return UtteranceType(label)
    except Exception as exc:
        logger.warning("LLM utterance classification failed, using heuristic: %s", exc)
        return classify_interviewer_utterance(text, previous_question)
