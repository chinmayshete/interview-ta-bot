"""
Live Interview Router

Exposes:
  POST /api/live/start               — create a live session
  GET  /api/live/{live_id}/state     — current state (HTTP poll fallback)
  POST /api/live/{live_id}/end       — stop the live session
  WS   /api/live/{live_id}/ws        — real-time event stream (WebSocket)
  POST /api/live/{live_id}/chunk     — push pre-transcribed chunk (text mode)
  POST /api/live/{live_id}/audio     — push raw audio chunk (STT mode)

DO NOT MODIFY any existing router.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave

import pyaudiowpatch as pyaudio
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from models.live_schemas import (
    ChunkTranscriptRequest,
    ConversationState,
    LiveEvent,
    LiveSessionInfo,
    LiveSessionState,
    LiveStateResponse,
    QuestionSource,
    QuestionStatus,
    StartLiveSessionRequest,
    Utterance,
)
from services import session_manager as parent_session_manager
from services import live_session_manager
from services.langgraph_agent import process_utterance_graph as process_utterance
from services.conversation_state_machine import check_silence
from services.live_question_generator import generate_live_next_question
from services.live_stt import transcribe_chunk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live-interview"])

# ── Per-session WebSocket connection registry ────────────────────────────────
# { live_session_id: set of active WebSocket connections }
_ws_connections: dict[str, set[WebSocket]] = {}

# ── Per-session loopback audio capture state ─────────────────────────────────
_loopback_state: dict[str, dict] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _broadcast(live_session_id: str, event: LiveEvent) -> None:
    """Broadcast a LiveEvent to all WebSocket clients of this session."""
    sockets = _ws_connections.get(live_session_id, set())
    if not sockets:
        return
    payload = event.model_dump_json()
    dead: set[WebSocket] = set()
    for ws in sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        sockets.discard(ws)


async def _on_candidate_done(state: LiveSessionState) -> list[LiveEvent]:
    """
    Callback invoked by check_silence() when candidate finishes answering.
    Runs question generation and returns the resulting events.
    """
    parent = parent_session_manager.get_session(state.parent_session_id or "")
    if parent is None:
        logger.error("[Live] Parent session not found: %s", state.parent_session_id)
        return []
    updated_state, events = await generate_live_next_question(state, parent)
    live_session_manager.set_live_session(updated_state)
    return events


async def _process_and_broadcast(
    live_id: str,
    utterance: Utterance,
) -> None:
    """
    Run the state machine for one utterance and broadcast all resulting events.
    """
    state = live_session_manager.get_live_session(live_id)
    if state is None:
        return

    updated_state, events = await process_utterance(state, utterance)
    live_session_manager.set_live_session(updated_state)

    for event in events:
        await _broadcast(live_id, event)


async def _silence_monitor(live_id: str) -> None:
    """
    Background task: polls every 200 ms to detect end-of-answer silence.
    Runs until the session is marked inactive.
    """
    while True:
        await asyncio.sleep(0.2)
        state = live_session_manager.get_live_session(live_id)
        if state is None or not state.is_live:
            break

        updated_state, events = await check_silence(
            state=state,
            now=time.time(),
            on_candidate_done=_on_candidate_done,
        )
        live_session_manager.set_live_session(updated_state)
        for event in events:
            await _broadcast(live_id, event)


# ── WASAPI Loopback chunk feeder ──────────────────────────────────────────────

async def _loopback_chunk_feeder(live_id: str) -> None:
    """
    Background task: reads frames from the WASAPI loopback buffer every second,
    assembles a WAV, sends to Azure STT, then feeds each DiarizedSegment into
    the state machine.
    """
    CHUNK_INTERVAL_S = 1.2   # how often to flush & transcribe

    while True:
        await asyncio.sleep(CHUNK_INTERVAL_S)

        lb = _loopback_state.get(live_id)
        if lb is None or not lb.get("is_recording"):
            break

        frames = lb.get("frames", [])
        if not frames:
            continue

        # Snapshot & clear the frame buffer atomically
        lb["frames"] = []
        chunk_frames = frames

        # Build WAV bytes from raw PCM frames
        wav_bytes = _frames_to_wav(
            frames=chunk_frames,
            sample_rate=lb["sample_rate"],
            channels=lb["channels"],
        )

        # Send to Azure STT (async, non-blocking)
        try:
            segments = await transcribe_chunk(wav_bytes, filename="chunk.wav")
        except Exception as exc:
            logger.error("[Loopback] STT failed: %s", exc)
            segments = []

        # Feed each segment into the state machine
        now = time.time()
        for seg in segments:
            utterance = Utterance(
                speaker_label=seg.speaker_label,
                text=seg.text,
                timestamp=seg.timestamp or now,
                duration_ms=seg.duration_ms,
            )
            await _process_and_broadcast(live_id, utterance)


def _frames_to_wav(frames: list[bytes], sample_rate: int, channels: int) -> bytes:
    """Convert raw PCM frames to an in-memory WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)   # paInt16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))
    return buf.getvalue()


# ── HTTP Endpoints ────────────────────────────────────────────────────────────

@router.post("/start", response_model=LiveSessionInfo)
async def start_live_session(req: StartLiveSessionRequest):
    """
    Create a live session linked to an existing parent session.
    The parent session (created via /api/interview/start) must exist.
    """
    parent = parent_session_manager.get_session(req.parent_session_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent session not found.")
    if not parent.is_active:
        raise HTTPException(status_code=400, detail="Parent session is not active.")

    live_id = live_session_manager.create_live_session(req.parent_session_id)
    _ws_connections[live_id] = set()

    return LiveSessionInfo(
        live_session_id=live_id,
        parent_session_id=req.parent_session_id,
        ws_url=f"ws://localhost:8000/api/live/{live_id}/ws",
    )


@router.get("/{live_id}/state", response_model=LiveStateResponse)
async def get_live_state(live_id: str):
    """HTTP polling fallback to get current live session state."""
    state = live_session_manager.get_live_session(live_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Live session not found.")
    return LiveStateResponse(
        live_session_id=live_id,
        conversation_state=state.conversation_state.value,
        active_question=state.active_question.text if state.active_question else None,
        question_source=state.active_question.source.value if state.active_question else None,
        question_status=state.active_question.status.value if state.active_question else None,
        speaker_roles=state.speaker_roles,
        transcript_buffer_size=len(state.transcript_buffer),
    )


@router.post("/{live_id}/end")
async def end_live_session(live_id: str):
    """Stop a live session and clean up audio capture."""
    state = live_session_manager.get_live_session(live_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Live session not found.")

    # Stop loopback if running
    lb = _loopback_state.pop(live_id, None)
    if lb:
        lb["is_recording"] = False
        stream = lb.get("stream")
        pya    = lb.get("pya")
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if pya:
            try:
                pya.terminate()
            except Exception:
                pass

    live_session_manager.end_live_session(live_id)

    # Notify connected clients
    await _broadcast(live_id, LiveEvent(
        session_id=live_id,
        event_type="session_ended",
        conversation_state=ConversationState.STATE_IDLE.value,
    ))

    return {"live_session_id": live_id, "status": "ended"}


@router.post("/{live_id}/start-capture")
async def start_loopback_capture(live_id: str):
    """
    Start WASAPI loopback capture for this live session.
    Audio is streamed in background and fed into the state machine automatically.
    """
    state = live_session_manager.get_live_session(live_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Live session not found.")
    if _loopback_state.get(live_id, {}).get("is_recording"):
        raise HTTPException(status_code=400, detail="Already capturing.")

    try:
        pya = pyaudio.PyAudio()
        wasapi_info = pya.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = pya.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

        if not default_speakers.get("isLoopbackDevice"):
            for loopback in pya.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    default_speakers = loopback
                    break

        frames_buf: list[bytes] = []

        def _callback(in_data, frame_count, time_info, status):
            frames_buf.append(in_data)
            return (in_data, pyaudio.paContinue)

        stream = pya.open(
            format=pyaudio.paInt16,
            channels=default_speakers["maxInputChannels"],
            rate=int(default_speakers["defaultSampleRate"]),
            frames_per_buffer=4096,
            input=True,
            input_device_index=default_speakers["index"],
            stream_callback=_callback,
        )

        _loopback_state[live_id] = {
            "is_recording": True,
            "frames": frames_buf,
            "stream": stream,
            "pya": pya,
            "sample_rate": int(default_speakers["defaultSampleRate"]),
            "channels": default_speakers["maxInputChannels"],
        }

        # Launch background tasks
        asyncio.create_task(_loopback_chunk_feeder(live_id))
        asyncio.create_task(_silence_monitor(live_id))

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to bind WASAPI loopback: {exc}",
        )

    return {"status": "capturing", "device": default_speakers["name"]}


@router.post("/{live_id}/stop-capture")
async def stop_loopback_capture(live_id: str):
    """Stop WASAPI loopback capture (session remains active for text-mode use)."""
    lb = _loopback_state.pop(live_id, None)
    if lb is None:
        raise HTTPException(status_code=400, detail="Not capturing.")

    lb["is_recording"] = False
    stream = lb.get("stream")
    pya    = lb.get("pya")
    if stream:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
    if pya:
        try:
            pya.terminate()
        except Exception:
            pass

    return {"status": "stopped"}


@router.post("/{live_id}/chunk")
async def push_chunk(live_id: str, req: ChunkTranscriptRequest):
    """
    Push a pre-transcribed utterance chunk into the pipeline.
    Use this when the frontend handles audio capture and STT itself.
    """
    state = live_session_manager.get_live_session(live_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Live session not found.")

    utterance = Utterance(
        speaker_label=req.speaker_label,
        text=req.text,
        timestamp=req.timestamp or time.time(),
        duration_ms=req.duration_ms,
    )
    await _process_and_broadcast(live_id, utterance)
    return {"status": "processed", "speaker_label": req.speaker_label}


@router.post("/{live_id}/audio")
async def push_audio_chunk(live_id: str):
    """
    Accept a raw audio chunk (multipart/form-data: file), run Azure STT,
    then feed the result into the state machine.
    Used when the frontend sends raw mic/loopback audio in chunks.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Use the /audio endpoint with multipart form. "
            "See push_audio_chunk_form() below."
        ),
    )


@router.post("/{live_id}/audio-chunk")
async def push_audio_chunk_form(live_id: str, request: Request):
    """
    Accept raw audio bytes (multipart form field 'audio'), run Azure STT
    with diarization, then feed each segment into the state machine.
    """
    state = live_session_manager.get_live_session(live_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Live session not found.")

    try:
        form = await request.form()
        audio_file = form.get("audio")
        if audio_file is None:
            raise HTTPException(status_code=400, detail="Missing 'audio' field.")
        audio_bytes = await audio_file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio chunk.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Form parse error: {exc}")

    segments = await transcribe_chunk(audio_bytes, filename=audio_file.filename or "chunk.wav")

    now = time.time()
    for seg in segments:
        utterance = Utterance(
            speaker_label=seg.speaker_label,
            text=seg.text,
            timestamp=seg.timestamp or now,
            duration_ms=seg.duration_ms,
        )
        await _process_and_broadcast(live_id, utterance)

    return {"status": "processed", "segments_count": len(segments)}


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@router.websocket("/{live_id}/ws")
async def websocket_endpoint(live_id: str, ws: WebSocket):
    """
    WebSocket connection for real-time event streaming.

    The client connects here and receives:
      - "transcript"     — live caption with speaker role
      - "state_change"   — conversation state transition
      - "next_question"  — bot-generated next question
      - "override"       — interviewer override event
      - "session_ended"  — session terminated
      - "error"          — processing error (non-fatal)

    The client MAY send JSON messages:
      { "type": "chunk", "speaker_label": "...", "text": "...", "timestamp": 0.0 }
    for text-mode injection.

    The UI only renders — all logic stays in the backend.
    """
    await ws.accept()

    state = live_session_manager.get_live_session(live_id)
    if state is None:
        await ws.send_text(LiveEvent(
            session_id=live_id,
            event_type="error",
            error="Live session not found.",
        ).model_dump_json())
        await ws.close()
        return

    # Register connection
    if live_id not in _ws_connections:
        _ws_connections[live_id] = set()
    _ws_connections[live_id].add(ws)

    # Send initial state snapshot
    await ws.send_text(LiveEvent(
        session_id=live_id,
        event_type="connected",
        conversation_state=state.conversation_state.value,
        active_question=state.active_question.text if state.active_question else None,
    ).model_dump_json())

    # Start silence monitor if not already running
    # (idempotent — asyncio.create_task won't duplicate if already running)
    asyncio.create_task(_silence_monitor(live_id))

    try:
        while True:
            raw = await ws.receive_text()

            # Parse incoming message from client (text-mode injection)
            try:
                import json as _json
                msg = _json.loads(raw)
            except Exception:
                continue

            if msg.get("type") == "chunk":
                utterance = Utterance(
                    speaker_label=msg.get("speaker_label", "speaker_0"),
                    text=msg.get("text", ""),
                    timestamp=msg.get("timestamp") or time.time(),
                    duration_ms=msg.get("duration_ms", 0),
                )
                if utterance.text.strip():
                    await _process_and_broadcast(live_id, utterance)

            elif msg.get("type") == "ping":
                await ws.send_text('{"event_type":"pong"}')

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected from live session %s", live_id)
    except Exception as exc:
        logger.error("[WS] Unexpected error in session %s: %s", live_id, exc)
    finally:
        _ws_connections.get(live_id, set()).discard(ws)
