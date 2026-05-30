"""
LangGraph Interview Agent

Replaces the hand-coded conversation_state_machine.py with an LLM-driven
LangGraph agent.  The agent receives each utterance and *reasons* about
what to do — no regex, no hardcoded if/else for classification.

Public API (drop-in replacement):
    async process_utterance_graph(state, utterance) -> (state, events)

Architecture:
    START → ingest_utterance → agent_decide ─┬─► handle_override    ─► emit_events → END
                                              ├─► set_new_question   ─► emit_events → END
                                              ├─► handle_collaborative ► emit_events → END
                                              ├─► accumulate_answer  ─► emit_events → END
                                              └─► emit_events ────────────────────── → END
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional, Any

import httpx
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

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

logger = logging.getLogger(__name__)

# ── Lazy-initialised LangChain LLM ──────────────────────────────────────────

_llm: AzureChatOpenAI | None = None


def _get_llm() -> AzureChatOpenAI:
    """Return a cached AzureChatOpenAI instance for agent reasoning."""
    global _llm
    if _llm is None:
        from config import get_settings
        settings = get_settings()
        _llm = AzureChatOpenAI(
            azure_deployment=settings.azure_gpt41_deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            api_key=settings.azure_openai_api_key,
            temperature=0,
            max_tokens=300,
            http_client=httpx.Client(
                verify=False,
                timeout=httpx.Timeout(30.0, connect=10.0),
            ),
        )
    return _llm


# ── LangGraph State Schema ──────────────────────────────────────────────────

class InterviewGraphState(TypedDict, total=False):
    # ── Inputs (set by caller) ───────────────────────────────────────────
    session_id: str
    utterance_text: str
    utterance_speaker: str
    utterance_timestamp: float
    utterance_duration_ms: int

    # Serialised LiveSessionState (mutated across nodes)
    live_state_dict: dict

    # ── Computed by ingest_utterance ─────────────────────────────────────
    speaker_role: str          # "interviewer" | "candidate" | "unknown"

    # ── Computed by agent_decide ─────────────────────────────────────────
    utterance_type: str        # "NEW_QUESTION" | "FOLLOWUP" | "HINT" | "CLARIFICATION" | "CANDIDATE_ANSWER"
    is_related_to_active: bool
    should_override: bool
    agent_reasoning: str

    # ── Output ───────────────────────────────────────────────────────────
    events: list[dict]


# ── Helper: build LiveEvent dict ─────────────────────────────────────────────

def _event_dict(session_id: str, event_type: str, **kwargs) -> dict:
    return LiveEvent(session_id=session_id, event_type=event_type, **kwargs).model_dump()


# ── Agent Reasoning Prompt ───────────────────────────────────────────────────

_AGENT_SYSTEM_PROMPT = """\
You are an AI analyzing a live interview conversation in real-time.
You receive one new utterance at a time and must classify it.

Your job is to decide:
1. utterance_type — one of: NEW_QUESTION, FOLLOWUP, HINT, CLARIFICATION, CANDIDATE_ANSWER
2. is_related_to_active — true/false (only relevant if utterance_type is NEW_QUESTION and there is an active question)
3. should_override — true/false (set true ONLY if: utterance_type is NEW_QUESTION AND is_related_to_active is false AND conversation_state is CANDIDATE_ANSWERING or COLLABORATIVE or PROCESSING)

Classification guide for INTERVIEWER utterances:
- HINT: guiding statements like "think about X", "consider Y", "keep in mind", or short non-question statements that help the candidate
- CLARIFICATION: "can you explain", "what do you mean", "tell me more", "could you elaborate"
- FOLLOWUP: a question about the same topic as the active question, often starting with "so", "building on that", "you mentioned"
- NEW_QUESTION: a fresh question on a different topic

For CANDIDATE utterances: always set utterance_type to CANDIDATE_ANSWER.
For UNKNOWN speakers: set utterance_type to CANDIDATE_ANSWER (safe default).

Return ONLY valid JSON with these exact keys:
{"utterance_type": "...", "is_related_to_active": true/false, "should_override": true/false, "reasoning": "brief explanation"}
"""


def _build_agent_prompt(
    speaker_role: str,
    text: str,
    conversation_state: str,
    active_question: str | None,
    recent_transcript: list[dict],
) -> str:
    """Build the user message for the agent reasoning call."""
    transcript_lines = []
    for entry in recent_transcript[-8:]:
        role_tag = entry.get("role", "?")
        transcript_lines.append(f"  [{role_tag}]: {entry['text'][:120]}")
    transcript_str = "\n".join(transcript_lines) if transcript_lines else "  (empty)"

    return f"""Current conversation state: {conversation_state}
Active question: {active_question or "(none)"}

Recent transcript:
{transcript_str}

New utterance by {speaker_role}:
"{text}"

Classify this utterance. Return JSON only."""


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH NODES
# ══════════════════════════════════════════════════════════════════════════════


def ingest_utterance(state: InterviewGraphState) -> dict:
    """
    Node 1: Buffer the utterance, infer speaker roles, emit transcript event.
    Pure logic — no LLM call.
    """
    live_state = LiveSessionState(**state["live_state_dict"])
    sid = live_state.session_id

    # Build Utterance and append to buffer
    utterance = Utterance(
        speaker_label=state["utterance_speaker"],
        text=state["utterance_text"],
        timestamp=state["utterance_timestamp"],
        duration_ms=state.get("utterance_duration_ms", 0),
    )
    live_state.transcript_buffer.append(utterance)
    live_state.last_speech_at = utterance.timestamp

    # Dynamic role inference
    infer_roles(live_state)
    role = get_role(live_state, utterance.speaker_label)

    if role == "interviewer":
        live_state.last_interviewer_speech_at = utterance.timestamp

    # Emit transcript event immediately (UI gets live captions regardless of LLM latency)
    events = [_event_dict(
        sid, "transcript",
        speaker_label=utterance.speaker_label,
        speaker_role=role,
        text=utterance.text,
        conversation_state=live_state.conversation_state.value,
        active_question=live_state.active_question.text if live_state.active_question else None,
    )]

    return {
        "live_state_dict": live_state.model_dump(),
        "speaker_role": role,
        "events": events,
    }


def agent_decide(state: InterviewGraphState) -> dict:
    """
    Node 2: LLM reasoning node — classifies the utterance and decides next action.
    Falls back to heuristic classifier if LLM fails.
    """
    role = state["speaker_role"]
    text = state["utterance_text"]
    live_state = LiveSessionState(**state["live_state_dict"])

    # ── Fast path: candidate or unknown → skip LLM ───────────────────────
    if role in ("candidate", "unknown"):
        return {
            "utterance_type": "CANDIDATE_ANSWER",
            "is_related_to_active": False,
            "should_override": False,
            "agent_reasoning": f"Speaker role is '{role}' — classified as candidate answer (no LLM needed).",
        }

    # ── Interviewer: use LLM for classification ──────────────────────────
    active_q = live_state.active_question.text if live_state.active_question else None

    # Build recent transcript context for the LLM
    recent_transcript = []
    for u in live_state.transcript_buffer[-8:]:
        u_role = get_role(live_state, u.speaker_label)
        recent_transcript.append({"role": u_role, "text": u.text})

    user_prompt = _build_agent_prompt(
        speaker_role=role,
        text=text,
        conversation_state=live_state.conversation_state.value,
        active_question=active_q,
        recent_transcript=recent_transcript,
    )

    try:
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=_AGENT_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content.strip()

        # Parse JSON from LLM response (handle markdown code fences)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        decision = json.loads(raw)
        utype = decision.get("utterance_type", "NEW_QUESTION").upper()
        is_related = decision.get("is_related_to_active", False)
        should_override = decision.get("should_override", False)
        reasoning = decision.get("reasoning", "")

        # Validate utterance_type
        valid_types = {"NEW_QUESTION", "FOLLOWUP", "HINT", "CLARIFICATION", "CANDIDATE_ANSWER"}
        if utype not in valid_types:
            utype = "NEW_QUESTION"

        logger.info(
            "[Agent] Decision: type=%s related=%s override=%s | '%s...' → %s",
            utype, is_related, should_override, text[:50], reasoning[:80],
        )

        return {
            "utterance_type": utype,
            "is_related_to_active": bool(is_related),
            "should_override": bool(should_override),
            "agent_reasoning": str(reasoning),
        }

    except Exception as exc:
        # ── Fallback to heuristic classifier ─────────────────────────────
        logger.warning("[Agent] LLM reasoning failed, falling back to heuristic: %s", exc)
        prev_q = live_state.active_question.text if live_state.active_question else None
        heuristic_type = classify_interviewer_utterance(text, previous_question=prev_q)

        # Approximate similarity check for override detection
        should_override_heuristic = False
        if heuristic_type in (UtteranceType.NEW_QUESTION, UtteranceType.FOLLOWUP):
            if live_state.active_question and live_state.conversation_state in (
                ConversationState.STATE_CANDIDATE_ANSWERING,
                ConversationState.STATE_COLLABORATIVE,
                ConversationState.STATE_PROCESSING,
            ):
                from services.similarity_checker import is_related_heuristic
                is_rel = is_related_heuristic(text, live_state.active_question.text)
                should_override_heuristic = not is_rel

        return {
            "utterance_type": heuristic_type.value,
            "is_related_to_active": not should_override_heuristic,
            "should_override": should_override_heuristic,
            "agent_reasoning": f"[heuristic fallback] classified as {heuristic_type.value}",
        }


def handle_override(state: InterviewGraphState) -> dict:
    """
    Node: Interviewer asked an unrelated new question → OVERRIDE.
    Abandon old question, reset answer chunks, set new question.
    """
    live_state = LiveSessionState(**state["live_state_dict"])
    sid = live_state.session_id
    events = list(state.get("events", []))

    # Mark old question abandoned
    old_q_text = live_state.active_question.text if live_state.active_question else ""
    if live_state.active_question:
        live_state.active_question.status = QuestionStatus.ABANDONED

    logger.info(
        "[Agent] OVERRIDE: abandoning '%s...' → new question '%s...'",
        old_q_text[:60], state["utterance_text"][:60],
    )

    events.append(_event_dict(
        sid, "override",
        text=f"Interviewer overrode. Abandoned: {old_q_text[:80]}",
        conversation_state=ConversationState.STATE_INTERVIEWER_ASKING.value,
        agent_reasoning=state.get("agent_reasoning", ""),
    ))

    # Reset answer accumulation
    live_state.current_answer_chunks = []
    live_state.interviewer_hints = []
    live_state.pending_bot_question = None

    # Set new active question
    live_state.active_question = ActiveQuestion(
        text=state["utterance_text"],
        source=QuestionSource.INTERVIEWER,
        status=QuestionStatus.ACTIVE,
        asked_at=state["utterance_timestamp"],
    )
    live_state.conversation_state = ConversationState.STATE_INTERVIEWER_ASKING

    events.append(_event_dict(
        sid, "state_change",
        conversation_state=ConversationState.STATE_INTERVIEWER_ASKING.value,
        active_question=state["utterance_text"],
        question_source=QuestionSource.INTERVIEWER.value,
        question_status=QuestionStatus.ACTIVE.value,
        agent_reasoning=state.get("agent_reasoning", ""),
    ))

    return {
        "live_state_dict": live_state.model_dump(),
        "events": events,
    }


def set_new_question(state: InterviewGraphState) -> dict:
    """
    Node: Interviewer asked a NEW_QUESTION or FOLLOWUP (not an override).
    Set as active question, transition to STATE_INTERVIEWER_ASKING.
    """
    live_state = LiveSessionState(**state["live_state_dict"])
    sid = live_state.session_id
    events = list(state.get("events", []))

    live_state.active_question = ActiveQuestion(
        text=state["utterance_text"],
        source=QuestionSource.INTERVIEWER,
        status=QuestionStatus.ACTIVE,
        asked_at=state["utterance_timestamp"],
    )
    live_state.conversation_state = ConversationState.STATE_INTERVIEWER_ASKING

    events.append(_event_dict(
        sid, "state_change",
        conversation_state=ConversationState.STATE_INTERVIEWER_ASKING.value,
        active_question=state["utterance_text"],
        question_source=QuestionSource.INTERVIEWER.value,
        question_status=QuestionStatus.ACTIVE.value,
        agent_reasoning=state.get("agent_reasoning", ""),
    ))

    return {
        "live_state_dict": live_state.model_dump(),
        "events": events,
    }


def handle_collaborative(state: InterviewGraphState) -> dict:
    """
    Node: Interviewer gave a HINT or CLARIFICATION while candidate is answering.
    Append hint, transition to STATE_COLLABORATIVE. Do NOT end the answer.
    """
    live_state = LiveSessionState(**state["live_state_dict"])
    sid = live_state.session_id
    events = list(state.get("events", []))
    current = live_state.conversation_state

    # Only enter collaborative if candidate was answering or already collaborative
    if current in (
        ConversationState.STATE_CANDIDATE_ANSWERING,
        ConversationState.STATE_COLLABORATIVE,
    ):
        live_state.interviewer_hints.append(state["utterance_text"])
        new_state = ConversationState.STATE_COLLABORATIVE

        if current != new_state:
            live_state.conversation_state = new_state
            events.append(_event_dict(
                sid, "state_change",
                conversation_state=new_state.value,
                active_question=live_state.active_question.text if live_state.active_question else None,
                agent_reasoning=state.get("agent_reasoning", ""),
            ))

    return {
        "live_state_dict": live_state.model_dump(),
        "events": events,
    }


def accumulate_answer(state: InterviewGraphState) -> dict:
    """
    Node: Candidate is speaking. Append to answer chunks, transition if needed.
    """
    live_state = LiveSessionState(**state["live_state_dict"])
    sid = live_state.session_id
    events = list(state.get("events", []))
    current = live_state.conversation_state

    # Accumulate answer text
    live_state.current_answer_chunks.append(state["utterance_text"])

    if current in (
        ConversationState.STATE_IDLE,
        ConversationState.STATE_INTERVIEWER_ASKING,
        ConversationState.STATE_COLLABORATIVE,
    ):
        live_state.conversation_state = ConversationState.STATE_CANDIDATE_ANSWERING
        events.append(_event_dict(
            sid, "state_change",
            conversation_state=ConversationState.STATE_CANDIDATE_ANSWERING.value,
            active_question=live_state.active_question.text if live_state.active_question else None,
            agent_reasoning=state.get("agent_reasoning", ""),
        ))

    return {
        "live_state_dict": live_state.model_dump(),
        "events": events,
    }


def emit_events(state: InterviewGraphState) -> dict:
    """
    Terminal node: no-op, just passes through.
    Events are already accumulated in the state by previous nodes.
    """
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL ROUTING
# ══════════════════════════════════════════════════════════════════════════════

def route_after_decide(state: InterviewGraphState) -> str:
    """Conditional edge: route to the appropriate action node based on the LLM decision."""
    role = state.get("speaker_role", "unknown")
    utype = state.get("utterance_type", "CANDIDATE_ANSWER")

    if role == "candidate" or role == "unknown":
        if role == "candidate":
            return "accumulate_answer"
        return "emit_events"

    # Interviewer
    if utype in ("HINT", "CLARIFICATION"):
        return "handle_collaborative"

    if state.get("should_override", False):
        return "handle_override"

    if utype in ("NEW_QUESTION", "FOLLOWUP"):
        return "set_new_question"

    # Fallback for unexpected types
    return "emit_events"


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH COMPILATION
# ══════════════════════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    """Build and compile the interview agent graph."""
    graph = StateGraph(InterviewGraphState)

    # Add nodes
    graph.add_node("ingest_utterance", ingest_utterance)
    graph.add_node("agent_decide", agent_decide)
    graph.add_node("handle_override", handle_override)
    graph.add_node("set_new_question", set_new_question)
    graph.add_node("handle_collaborative", handle_collaborative)
    graph.add_node("accumulate_answer", accumulate_answer)
    graph.add_node("emit_events", emit_events)

    # Edges
    graph.add_edge(START, "ingest_utterance")
    graph.add_edge("ingest_utterance", "agent_decide")

    # Conditional routing after LLM decision
    graph.add_conditional_edges(
        "agent_decide",
        route_after_decide,
        {
            "handle_override": "handle_override",
            "set_new_question": "set_new_question",
            "handle_collaborative": "handle_collaborative",
            "accumulate_answer": "accumulate_answer",
            "emit_events": "emit_events",
        },
    )

    # All action nodes flow to emit_events → END
    graph.add_edge("handle_override", "emit_events")
    graph.add_edge("set_new_question", "emit_events")
    graph.add_edge("handle_collaborative", "emit_events")
    graph.add_edge("accumulate_answer", "emit_events")
    graph.add_edge("emit_events", END)

    return graph.compile()


# Compile once at module level
_interview_agent = _build_graph()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — drop-in replacement for conversation_state_machine.process_utterance
# ══════════════════════════════════════════════════════════════════════════════

async def process_utterance_graph(
    state: LiveSessionState,
    utterance: Utterance,
    llm_client=None,        # unused — LangGraph manages its own LLM
    deployment: str = "",    # unused — kept for signature compatibility
    use_llm_similarity: bool = False,  # unused
) -> tuple[LiveSessionState, list[LiveEvent]]:
    """
    Process one utterance through the LangGraph interview agent.

    Drop-in replacement for conversation_state_machine.process_utterance().
    Same signature, same return type.

    The LLM reasoning happens inside the graph's agent_decide node.
    If the LLM fails, it falls back to the heuristic classifier.
    """
    # Prepare graph input
    graph_input: InterviewGraphState = {
        "session_id": state.session_id,
        "utterance_text": utterance.text,
        "utterance_speaker": utterance.speaker_label,
        "utterance_timestamp": utterance.timestamp,
        "utterance_duration_ms": utterance.duration_ms,
        "live_state_dict": state.model_dump(),
        "speaker_role": "",
        "utterance_type": "",
        "is_related_to_active": False,
        "should_override": False,
        "agent_reasoning": "",
        "events": [],
    }

    # Run the graph asynchronously (nodes are sync but graph invocation is async-safe)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _interview_agent.invoke, graph_input)

    # Extract outputs
    updated_state = LiveSessionState(**result["live_state_dict"])
    event_dicts = result.get("events", [])

    # Convert event dicts back to LiveEvent models
    events = []
    for ed in event_dicts:
        try:
            events.append(LiveEvent(**ed))
        except Exception:
            events.append(LiveEvent(
                session_id=state.session_id,
                event_type=ed.get("event_type", "error"),
                error=f"Failed to parse event: {ed}",
            ))

    return updated_state, events
