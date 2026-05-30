"""
Live Question Generator

Generates the next interview question after the candidate finishes answering.

Reuses the existing interview_engine.generate_next_turn() so the adaptive
difficulty, history tracking and prompt logic are all shared — no duplication.

This module only adds:
  - Guard: do NOT generate if the interviewer has overridden
  - Async wrapper: wraps the sync engine call in a thread pool executor
  - Event building: wraps the result in a LiveEvent for the WebSocket
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from models.live_schemas import (
    LiveSessionState,
    LiveEvent,
    ActiveQuestion,
    QuestionSource,
    QuestionStatus,
    ConversationState,
)

logger = logging.getLogger(__name__)


async def generate_live_next_question(
    live_state: LiveSessionState,
    parent_session,             # InterviewState from the existing session_manager
) -> tuple[LiveSessionState, list[LiveEvent]]:
    """
    Called when the state machine reaches STATE_PROCESSING.

    Parameters
    ----------
    live_state : LiveSessionState
        The live session state.
    parent_session : InterviewState
        The parent session from session_manager.get_session().
        Used to read resume, jd, history for the LLM call.

    Returns
    -------
    (updated_live_state, events_to_broadcast)
    """
    # Lazy import to avoid circular dependency at module load time
    from services.interview_engine import generate_next_turn
    from services import session_manager

    events: list[LiveEvent] = []
    sid = live_state.session_id

    # ── Guard: interviewer has overridden (active question source changed) ──
    if (
        live_state.active_question
        and live_state.active_question.source == QuestionSource.INTERVIEWER
        and live_state.active_question.status == QuestionStatus.ABANDONED
    ):
        logger.info("[QGen] Skipping — active question was overridden/abandoned.")
        live_state.conversation_state = ConversationState.STATE_IDLE
        return live_state, events

    # ── Guard: no answer accumulated ────────────────────────────────────────
    full_answer = " ".join(live_state.current_answer_chunks).strip()
    if not full_answer:
        logger.info("[QGen] Skipping — no candidate answer accumulated.")
        live_state.conversation_state = ConversationState.STATE_IDLE
        return live_state, events

    current_question = live_state.active_question.text if live_state.active_question else ""
    hints = live_state.interviewer_hints

    # Build state summary string (same format as existing session_manager.get_state_summary)
    state_summary = session_manager.get_state_summary(parent_session.session_id)

    # ── Generate next question (sync call → thread pool) ────────────────────
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: generate_next_turn(
                resume=parent_session.resume_text,
                jd=parent_session.jd_text,
                last_question=current_question,
                candidate_answer=full_answer
                + ("\n\nInterviewer hints during answer: " + "; ".join(hints) if hints else ""),
                interview_state=state_summary,
            ),
        )
    except Exception as exc:
        logger.error("[QGen] LLM call failed: %s", exc)
        live_state.conversation_state = ConversationState.STATE_IDLE
        events.append(LiveEvent(
            session_id=sid,
            event_type="error",
            error=f"Question generation failed: {exc}",
        ))
        return live_state, events

    # ── Update parent session history ────────────────────────────────────────
    eval_data = result.get("evaluation", {})
    next_q    = result.get("next_question", {})

    try:
        session_manager.update_session(
            session_id=parent_session.session_id,
            question=current_question,
            answer=full_answer,
            rating=eval_data.get("rating", "partial"),
            difficulty=next_q.get("difficulty", "easy"),
            category=next_q.get("category", "technical"),
        )
    except Exception as exc:
        logger.warning("[QGen] Could not update parent session history: %s", exc)

    # ── Set the bot question as pending active question ──────────────────────
    bot_question_text = next_q.get("question", "")
    live_state.pending_bot_question = bot_question_text

    # Mark current question as answered
    if live_state.active_question:
        live_state.active_question.status = QuestionStatus.ANSWERED

    # Reset accumulation for next turn
    live_state.current_answer_chunks = []
    live_state.interviewer_hints     = []

    # Transition back to idle — interviewer decides whether to use the suggestion
    live_state.conversation_state = ConversationState.STATE_IDLE

    # ── Build event for UI ───────────────────────────────────────────────────
    events.append(LiveEvent(
        session_id=sid,
        event_type="next_question",
        next_question=result,
        expected_answer=result.get("expected_answer"),
        active_question=bot_question_text,
        question_source=QuestionSource.BOT.value,
        question_status=QuestionStatus.ACTIVE.value,
        conversation_state=ConversationState.STATE_IDLE.value,
    ))

    events.append(LiveEvent(
        session_id=sid,
        event_type="state_change",
        conversation_state=ConversationState.STATE_IDLE.value,
    ))

    logger.info("[QGen] Generated bot question: '%s...'", bot_question_text[:80])
    return live_state, events
