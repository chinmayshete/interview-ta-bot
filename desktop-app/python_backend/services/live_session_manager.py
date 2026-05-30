"""
Live session manager — in-memory store for real-time interview sessions.

Completely separate from the existing session_manager.py.
No modifications to existing code.
"""

from __future__ import annotations

import uuid
import time
from typing import Optional

from models.live_schemas import LiveSessionState, ConversationState


# { live_session_id: LiveSessionState }
_live_sessions: dict[str, LiveSessionState] = {}


def create_live_session(parent_session_id: str) -> str:
    """
    Create a new live session linked to an existing parent session.
    Returns the new live_session_id.
    """
    live_id = "live_" + uuid.uuid4().hex[:10]
    state = LiveSessionState(
        session_id=live_id,
        parent_session_id=parent_session_id,
        is_live=True,
        last_speech_at=time.time(),
        last_interviewer_speech_at=time.time(),
    )
    _live_sessions[live_id] = state
    return live_id


def get_live_session(live_session_id: str) -> Optional[LiveSessionState]:
    return _live_sessions.get(live_session_id)


def set_live_session(state: LiveSessionState) -> None:
    """Persist the updated state object back into the store."""
    _live_sessions[state.session_id] = state


def end_live_session(live_session_id: str) -> None:
    state = _live_sessions.get(live_session_id)
    if state:
        state.is_live = False
        state.conversation_state = ConversationState.STATE_IDLE
        _live_sessions[live_session_id] = state


def list_live_sessions() -> list[str]:
    return list(_live_sessions.keys())
