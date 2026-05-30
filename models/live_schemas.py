"""
Live interview Pydantic models.

All NEW models for the real-time conversation pipeline.
Zero changes to the existing models/schemas.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Conversation states ───────────────────────────────────────────────────────

class ConversationState(str, Enum):
    STATE_IDLE              = "STATE_IDLE"
    STATE_INTERVIEWER_ASKING = "STATE_INTERVIEWER_ASKING"
    STATE_CANDIDATE_ANSWERING = "STATE_CANDIDATE_ANSWERING"
    STATE_COLLABORATIVE      = "STATE_COLLABORATIVE"
    STATE_PROCESSING         = "STATE_PROCESSING"


# ── Utterance classifications ─────────────────────────────────────────────────

class UtteranceType(str, Enum):
    NEW_QUESTION   = "NEW_QUESTION"
    FOLLOWUP       = "FOLLOWUP"
    HINT           = "HINT"
    CLARIFICATION  = "CLARIFICATION"
    CANDIDATE_ANSWER = "CANDIDATE_ANSWER"   # not an interviewer type, used for typing
    UNKNOWN        = "UNKNOWN"


# ── Question source and status ────────────────────────────────────────────────

class QuestionSource(str, Enum):
    INTERVIEWER = "INTERVIEWER"
    BOT         = "BOT"


class QuestionStatus(str, Enum):
    ACTIVE    = "ACTIVE"
    ANSWERED  = "ANSWERED"
    ABANDONED = "ABANDONED"


# ── A single transcribed utterance ───────────────────────────────────────────

class Utterance(BaseModel):
    speaker_label: str          # "speaker_0", "speaker_1", etc. (from Azure diarization)
    text: str
    timestamp: float            # epoch seconds
    duration_ms: int = 0


# ── The tracked current question ─────────────────────────────────────────────

class ActiveQuestion(BaseModel):
    text: str
    source: QuestionSource = QuestionSource.INTERVIEWER
    status: QuestionStatus = QuestionStatus.ACTIVE
    asked_at: float = 0.0       # epoch seconds


# ── Full live-session state ───────────────────────────────────────────────────

class LiveSessionState(BaseModel):
    """
    In-memory state for one live (real-time) interview session.

    Lifecycle:
      created by live_session_manager.create_live_session()
      mutated in place by the conversation state machine
    """
    session_id: str

    # Conversation state machine
    conversation_state: ConversationState = ConversationState.STATE_IDLE

    # Speaker role map  { azure_speaker_label: "interviewer" | "candidate" }
    # Populated dynamically; never hardcoded.
    speaker_roles: dict[str, str] = Field(default_factory=dict)

    # Rolling transcript buffer (ordered, newest at end)
    transcript_buffer: list[Utterance] = Field(default_factory=list)

    # The question currently being answered (or just asked)
    active_question: Optional[ActiveQuestion] = None

    # Accumulated candidate answer text for the current question
    current_answer_chunks: list[str] = Field(default_factory=list)

    # Hints given by the interviewer while the candidate was answering
    interviewer_hints: list[str] = Field(default_factory=list)

    # Timestamps for silence detection
    last_speech_at: float = 0.0         # epoch time of the most recent audio chunk
    last_interviewer_speech_at: float = 0.0

    # Consecutive utterance counters for dynamic role inference
    speaker_utterance_counts: dict[str, int] = Field(default_factory=dict)

    # The generated-but-not-yet-delivered bot question (pending interviewer override window)
    pending_bot_question: Optional[str] = None

    # Whether we are streaming (WASAPI loopback active)
    is_live: bool = False

    # Link back to the parent session in the existing session_manager
    parent_session_id: Optional[str] = None


# ── WebSocket event envelope ──────────────────────────────────────────────────

class LiveEvent(BaseModel):
    """
    Single JSON frame pushed over the WebSocket to the UI.
    UI should only render this data — no logic on the frontend.
    """
    event_type: str          # "transcript" | "state_change" | "next_question" | "error"
    session_id: str

    # transcript event
    speaker_label: Optional[str] = None
    speaker_role: Optional[str] = None   # "interviewer" | "candidate" | "unknown"
    text: Optional[str] = None

    # state event
    conversation_state: Optional[str] = None

    # active question tracking
    active_question: Optional[str] = None
    question_source: Optional[str] = None
    question_status: Optional[str] = None

    # generated question
    next_question: Optional[dict] = None     # full InterviewResponse-style dict
    expected_answer: Optional[str] = None

    # error
    error: Optional[str] = None


# ── HTTP request / response models ───────────────────────────────────────────

class StartLiveSessionRequest(BaseModel):
    """
    Attach a live (real-time) layer on top of an existing session.
    The parent session must already exist (created via /api/interview/start).
    """
    parent_session_id: str      # existing session from session_manager


class LiveSessionInfo(BaseModel):
    live_session_id: str
    parent_session_id: str
    ws_url: str                 # e.g. "ws://localhost:8000/api/live/{live_session_id}/ws"


class ChunkTranscriptRequest(BaseModel):
    """
    Push a pre-transcribed chunk (text + diarization) into the pipeline.
    Used when the caller handles audio capture / STT externally.
    """
    speaker_label: str
    text: str
    timestamp: float
    duration_ms: int = 0


class LiveStateResponse(BaseModel):
    live_session_id: str
    conversation_state: str
    active_question: Optional[str]
    question_source: Optional[str]
    question_status: Optional[str]
    speaker_roles: dict[str, str]
    transcript_buffer_size: int
