"""
Session manager — in-memory interview session store.

Tracks the full interview state per session and auto-adjusts difficulty
based on rolling evaluation ratings.
"""

from __future__ import annotations

import uuid
from models.schemas import (
    Difficulty,
    HistoryEntry,
    InterviewState,
    Rating,
    InterviewSummary,
)


# In-memory session store  {session_id: InterviewState}
_sessions: dict[str, InterviewState] = {}


def create_session(resume_text: str, jd_text: str) -> str:
    """Create a new interview session and return its ID."""
    session_id = uuid.uuid4().hex[:12]
    state = InterviewState(
        session_id=session_id,
        resume_text=resume_text,
        jd_text=jd_text,
        is_active=True,
    )
    _sessions[session_id] = state
    return session_id


def get_session(session_id: str) -> InterviewState | None:
    """Get a session by ID, or None if not found."""
    return _sessions.get(session_id)


def update_session(
    session_id: str,
    question: str,
    answer: str,
    rating: str,
    difficulty: str,
    category: str,
) -> InterviewState:
    """
    Record the latest Q&A exchange and auto-adjust difficulty.

    Parameters
    ----------
    session_id : str
    question : str      – The question that was asked.
    answer : str        – The candidate's answer.
    rating : str        – "strong" | "partial" | "weak".
    difficulty : str    – "easy" | "medium" | "hard".
    category : str      – "technical" | "behavioral" | ...
    """
    state = _sessions[session_id]

    # Record history
    entry = HistoryEntry(
        question=question,
        answer=answer,
        rating=Rating(rating),
        difficulty=Difficulty(difficulty),
        category=category,
    )
    state.history.append(entry)
    state.question_count += 1

    # Track topics
    if category not in state.topics_covered:
        state.topics_covered.append(category)

    # ── Adaptive difficulty logic ────────────────────────────────────────
    r = Rating(rating)

    if r == Rating.STRONG:
        state.consecutive_strong += 1
        state.consecutive_weak = 0
    elif r == Rating.WEAK:
        state.consecutive_weak += 1
        state.consecutive_strong = 0
    else:  # partial
        state.consecutive_weak = 0
        state.consecutive_strong = 0

    # Escalate difficulty after 2 consecutive strong answers
    if state.consecutive_strong >= 2:
        if state.current_difficulty == Difficulty.EASY:
            state.current_difficulty = Difficulty.MEDIUM
        elif state.current_difficulty == Difficulty.MEDIUM:
            state.current_difficulty = Difficulty.HARD
        state.consecutive_strong = 0  # reset counter

    # De-escalate difficulty after 2 consecutive weak answers
    if state.consecutive_weak >= 2:
        if state.current_difficulty == Difficulty.HARD:
            state.current_difficulty = Difficulty.MEDIUM
        elif state.current_difficulty == Difficulty.MEDIUM:
            state.current_difficulty = Difficulty.EASY
        state.consecutive_weak = 0

    _sessions[session_id] = state
    return state


def get_state_summary(session_id: str) -> str:
    """Return a compact JSON-like summary of the session state for the LLM."""
    state = _sessions.get(session_id)
    if not state:
        return "{}"

    recent = []
    for h in state.history[-5:]:  # last 5 exchanges
        recent.append({
            "q": h.question[:120],
            "rating": h.rating.value,
            "difficulty": h.difficulty.value,
        })

    return str({
        "question_count": state.question_count,
        "current_difficulty": state.current_difficulty.value,
        "topics_covered": state.topics_covered,
        "consecutive_weak": state.consecutive_weak,
        "consecutive_strong": state.consecutive_strong,
        "recent_history": recent,
    })


def end_session(session_id: str) -> None:
    """Mark a session as inactive."""
    if session_id in _sessions:
        _sessions[session_id].is_active = False


def save_summary(session_id: str, summary: InterviewSummary) -> None:
    """Save the final performance summary to the session state."""
    if session_id in _sessions:
        _sessions[session_id].summary = summary
