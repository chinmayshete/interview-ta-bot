"""
Conversation State Machine

Processes each incoming Utterance and drives state transitions:

  STATE_IDLE
    └─ interviewer speaks NEW_QUESTION ──────────────────► STATE_INTERVIEWER_ASKING
    
  STATE_INTERVIEWER_ASKING
    └─ candidate starts speaking (or silence > 800 ms) ──► STATE_CANDIDATE_ANSWERING

  STATE_CANDIDATE_ANSWERING
    ├─ interviewer HINT / CLARIFICATION ─────────────────► STATE_COLLABORATIVE
    ├─ interviewer NEW_QUESTION (unrelated) ─────────────► OVERRIDE → STATE_INTERVIEWER_ASKING
    └─ silence > 1500 ms + sentence complete ────────────► STATE_PROCESSING

  STATE_COLLABORATIVE
    └─ candidate resumes ────────────────────────────────► STATE_CANDIDATE_ANSWERING
    └─ interviewer NEW_QUESTION (unrelated) ─────────────► OVERRIDE → STATE_INTERVIEWER_ASKING

  STATE_PROCESSING
    └─ (async) generate next question ──────────────────► STATE_IDLE (ready for next turn)

This module is pure logic — no I/O.
The WebSocket router calls process_utterance() and broadcasts the returned events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Callable, Awaitable

from models.live_schemas import (
    ConversationState,
    LiveSessionState,
    Utterance,
    UtteranceType,
    ActiveQuestion,
    QuestionSource,
    QuestionStatus,
    LiveEvent,
)
from services.speaker_role_mapper import infer_roles, get_role
from services.utterance_classifier import classify_interviewer_utterance
from services.similarity_checker import check_similarity

logger = logging.getLogger(__name__)

# ── Timing thresholds ─────────────────────────────────────────────────────────
SILENCE_CANDIDATE_DONE_MS    = 1500   # silence after which candidate is considered done
SILENCE_CANDIDATE_STARTS_MS  = 800    # silence after which candidate is expected to start
HINT_WORD_LIMIT              = 20     # utterances below this are treated as hints if guiding


# ── Helper: build LiveEvent ───────────────────────────────────────────────────

def _event(session_id: str, event_type: str, **kwargs) -> LiveEvent:
    return LiveEvent(session_id=session_id, event_type=event_type, **kwargs)


# ── Main entry point ──────────────────────────────────────────────────────────

async def process_utterance(
    state: LiveSessionState,
    utterance: Utterance,
    llm_client=None,
    deployment: str = "",
    use_llm_similarity: bool = False,
) -> tuple[LiveSessionState, list[LiveEvent]]:
    """
    Process one incoming utterance through the state machine.

    Parameters
    ----------
    state : LiveSessionState
        Current session state (will be mutated and returned).
    utterance : Utterance
        The incoming transcription chunk.
    llm_client : AzureOpenAI | None
        Optional LLM client for similarity & classification fallback.
    deployment : str
        Deployment name for optional LLM calls.
    use_llm_similarity : bool
        Whether to use LLM for similarity checks (adds latency).

    Returns
    -------
    (updated_state, events_to_broadcast)
    """
    events: list[LiveEvent] = []
    sid = state.session_id

    # ── 1. Append to transcript buffer ──────────────────────────────────────
    state.transcript_buffer.append(utterance)
    state.last_speech_at = utterance.timestamp

    # ── 2. Dynamic role inference ────────────────────────────────────────────
    infer_roles(state)
    role = get_role(state, utterance.speaker_label)

    if role == "interviewer":
        state.last_interviewer_speech_at = utterance.timestamp

    # Broadcast transcript event (UI renders live captions)
    events.append(_event(
        sid, "transcript",
        speaker_label=utterance.speaker_label,
        speaker_role=role,
        text=utterance.text,
        conversation_state=state.conversation_state.value,
        active_question=state.active_question.text if state.active_question else None,
    ))

    # ── 3. State machine transitions ─────────────────────────────────────────

    current_state = state.conversation_state

    # ────────────────────────────────────────────────────────────────────────
    # A. INTERVIEWER speaks
    # ────────────────────────────────────────────────────────────────────────
    if role == "interviewer":
        utype = classify_interviewer_utterance(
            utterance.text,
            previous_question=state.active_question.text if state.active_question else None,
        )

        # ── A1. HINT or CLARIFICATION while candidate was answering ─────────
        if utype in (UtteranceType.HINT, UtteranceType.CLARIFICATION):
            if current_state in (
                ConversationState.STATE_CANDIDATE_ANSWERING,
                ConversationState.STATE_COLLABORATIVE,
            ):
                state.interviewer_hints.append(utterance.text)
                new_state = ConversationState.STATE_COLLABORATIVE
                if state.conversation_state != new_state:
                    state.conversation_state = new_state
                    events.append(_event(
                        sid, "state_change",
                        conversation_state=new_state.value,
                        active_question=state.active_question.text if state.active_question else None,
                    ))
                return state, events

        # ── A2. NEW_QUESTION or FOLLOWUP ────────────────────────────────────
        if utype in (UtteranceType.NEW_QUESTION, UtteranceType.FOLLOWUP):

            # Check semantic similarity if there's already an active question
            is_related = False
            if state.active_question:
                is_related = await check_similarity(
                    new_question=utterance.text,
                    current_question=state.active_question.text,
                    llm_client=llm_client,
                    deployment=deployment,
                    use_llm=use_llm_similarity,
                )

            # ── OVERRIDE: unrelated new question ────────────────────────────
            if (
                state.active_question
                and not is_related
                and current_state in (
                    ConversationState.STATE_CANDIDATE_ANSWERING,
                    ConversationState.STATE_COLLABORATIVE,
                    ConversationState.STATE_PROCESSING,
                )
            ):
                # Mark old question abandoned
                state.active_question.status = QuestionStatus.ABANDONED
                logger.info(
                    "[SM] OVERRIDE: abandoning '%s...' → new question '%s...'",
                    state.active_question.text[:60],
                    utterance.text[:60],
                )
                events.append(_event(
                    sid, "override",
                    text=f"Interviewer overrode. Abandoned: {state.active_question.text[:80]}",
                    conversation_state=ConversationState.STATE_INTERVIEWER_ASKING.value,
                ))
                # Reset answer accumulation
                state.current_answer_chunks = []
                state.interviewer_hints = []
                state.pending_bot_question = None

            # Set new active question
            state.active_question = ActiveQuestion(
                text=utterance.text,
                source=QuestionSource.INTERVIEWER,
                status=QuestionStatus.ACTIVE,
                asked_at=utterance.timestamp,
            )
            state.conversation_state = ConversationState.STATE_INTERVIEWER_ASKING
            events.append(_event(
                sid, "state_change",
                conversation_state=ConversationState.STATE_INTERVIEWER_ASKING.value,
                active_question=utterance.text,
                question_source=QuestionSource.INTERVIEWER.value,
                question_status=QuestionStatus.ACTIVE.value,
            ))

        return state, events

    # ────────────────────────────────────────────────────────────────────────
    # B. CANDIDATE speaks
    # ────────────────────────────────────────────────────────────────────────
    if role == "candidate":
        # Accumulate answer
        state.current_answer_chunks.append(utterance.text)

        if current_state in (
            ConversationState.STATE_IDLE,
            ConversationState.STATE_INTERVIEWER_ASKING,
            ConversationState.STATE_COLLABORATIVE,
        ):
            state.conversation_state = ConversationState.STATE_CANDIDATE_ANSWERING
            events.append(_event(
                sid, "state_change",
                conversation_state=ConversationState.STATE_CANDIDATE_ANSWERING.value,
                active_question=state.active_question.text if state.active_question else None,
            ))

        return state, events

    # ── Unknown speaker: buffer only, no state change ────────────────────────
    return state, events


# ── Silence detector — called on a timer from the WebSocket router ────────────

async def check_silence(
    state: LiveSessionState,
    now: float,
    on_candidate_done: Callable[[LiveSessionState], Awaitable[list[LiveEvent]]],
) -> tuple[LiveSessionState, list[LiveEvent]]:
    """
    Check elapsed silence and trigger processing if thresholds are crossed.

    Parameters
    ----------
    state : LiveSessionState
    now : float
        Current epoch time in seconds.
    on_candidate_done : async callable
        Called when candidate is deemed to have finished answering.
        Receives the current state and returns events to broadcast.

    Returns
    -------
    (updated_state, events)
    """
    events: list[LiveEvent] = []
    silence_ms = (now - state.last_speech_at) * 1000

    if (
        state.conversation_state == ConversationState.STATE_CANDIDATE_ANSWERING
        and silence_ms >= SILENCE_CANDIDATE_DONE_MS
        and state.current_answer_chunks
    ):
        # Candidate has finished — move to processing
        state.conversation_state = ConversationState.STATE_PROCESSING
        events.append(_event(
            state.session_id, "state_change",
            conversation_state=ConversationState.STATE_PROCESSING.value,
            active_question=state.active_question.text if state.active_question else None,
        ))
        # Delegate question generation to the caller
        gen_events = await on_candidate_done(state)
        events.extend(gen_events)

    return state, events
