"""
Interview routes — manage session lifecycle, Q&A turns, and transcription.
"""

from typing import Optional, Union
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import Response
from models.schemas import InterviewStartRequest, InterviewTurnRequest, InterviewSummary
from services import session_manager
from services.interview_engine import (
    generate_first_question, 
    generate_next_turn, 
    correct_text_spelling,
    generate_overall_summary
)
from services.transcription import transcribe_audio
from services.exporter import InterviewExporter

router = APIRouter(prefix="/api/interview", tags=["interview"])


@router.post("/start")
async def start_interview(req: InterviewStartRequest):
    """
    Initialise a new interview session and generate the first question.

    Expects: resume_text, jd_text (already extracted).
    """
    if not req.resume_text.strip():
        raise HTTPException(status_code=400, detail="Resume text is empty.")
    if not req.jd_text.strip():
        raise HTTPException(status_code=400, detail="JD text is empty.")

    session_id = session_manager.create_session(req.resume_text, req.jd_text)

    # Generate the opening question
    try:
        result = generate_first_question(req.resume_text, req.jd_text)
    except Exception as exc:
        # If the Azure API crashes, gracefully return the exact error
        raise HTTPException(status_code=500, detail=f"Azure OpenAI Error: {str(exc)}")

    # Update session with the first question (no real answer yet)
    return {"session_id": session_id, **result}


@router.post("/next")
async def next_turn(req: InterviewTurnRequest):
    """
    Submit the candidate's answer for the current question and receive
    the evaluation + next question.
    """
    state = session_manager.get_session(req.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not state.is_active:
        raise HTTPException(status_code=400, detail="Interview session has ended.")

    # The last question is the most recent one in history, or from the start response
    last_question = ""
    if state.history:
        last_question = state.history[-1].question

    state_summary = session_manager.get_state_summary(req.session_id)

    try:
        result = generate_next_turn(
            resume=state.resume_text,
            jd=state.jd_text,
            last_question=last_question,
            candidate_answer=req.candidate_answer,
            interview_state=state_summary,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Azure OpenAI Error: {str(exc)}")

    # Update state with this exchange
    eval_data = result.get("evaluation", {})
    next_q = result.get("next_question", {})

    session_manager.update_session(
        session_id=req.session_id,
        question=last_question,
        answer=req.candidate_answer,
        rating=eval_data.get("rating", "partial"),
        difficulty=next_q.get("difficulty", "easy"),
        category=next_q.get("category", "technical"),
    )

    return {"session_id": req.session_id, **result}


@router.post("/transcribe")
async def transcribe(request: Request):
    """
    Manually parse the form to avoid strict FastAPI validation 
    and provide better error reporting.
    """
    try:
        form = await request.form()
        session_id = form.get("session_id")
        raw_text = form.get("raw_text")
        audio = form.get("audio") # This will be an UploadFile or None

        print(f"DEBUG: /transcribe manually called. session_id={session_id}, has_text={bool(raw_text)}, has_audio={bool(audio)}")

        if not session_id:
            raise HTTPException(status_code=400, detail="Missing session_id in form data.")

        state = session_manager.get_session(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")

        if raw_text:
            text = correct_text_spelling(str(raw_text))
        elif audio and isinstance(audio, UploadFile):
            audio_bytes = await audio.read()
            if len(audio_bytes) == 0:
                raise HTTPException(status_code=400, detail="Audio file is empty.")
            text = await transcribe_audio(audio_bytes, filename=audio.filename or "audio.webm")
        else:
            raise HTTPException(status_code=400, detail="No audio or text provided in form data.")

        return {"session_id": session_id, "text": text}

    except HTTPException:
        raise
    except Exception as exc:
        print(f"DEBUG: Transcription error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/state/{session_id}")
async def get_state(session_id: str):
    """Return the current interview state."""
    state = session_manager.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return state.model_dump(exclude={"resume_text", "jd_text"})


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """Return the full Q&A history for a session."""
    state = session_manager.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    history = [entry.model_dump() for entry in state.history]
    return {"session_id": session_id, "history": history, "count": len(history)}


@router.post("/end/{session_id}")
async def end_interview(session_id: str):
    """End an active interview session."""
    state = session_manager.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    session_manager.end_session(session_id)
    return {"session_id": session_id, "status": "ended"}


@router.get("/summary/{session_id}")
async def get_summary(session_id: str):
    """
    Generate or retrieve the overall performance summary for a completed interview.
    """
    state = session_manager.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    # If already generated, return cached
    if state.summary:
        return state.summary

    # History is required to generate a summary
    if not state.history:
        raise HTTPException(status_code=400, detail="Cannot generate summary for an empty interview.")

    try:
        # Prepare history for the LLM
        history_list = [h.model_dump() for h in state.history]
        result = generate_overall_summary(state.resume_text, state.jd_text, history_list)
        
        # Parse and save
        summary = InterviewSummary(**result)
        session_manager.save_summary(session_id, summary)
        return summary
    except Exception as exc:
        print(f"DEBUG: Summary error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/export/{session_id}/{export_format}")
async def export_interview(session_id: str, export_format: str):
    """
    Export the interview performance report as PDF or DOCX.
    """
    state = session_manager.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    if not state.summary:
        # Attempt to auto-generate if missing
        await get_summary(session_id)
        state = session_manager.get_session(session_id)

    history_list = [h.model_dump() for h in state.history]
    
    if export_format.lower() == "pdf":
        file_bytes = InterviewExporter.generate_pdf(state.summary.model_dump(), history_list)
        media_type = "application/pdf"
        filename = f"Interview_Report_{session_id}.pdf"
    elif export_format.lower() == "docx":
        file_bytes = InterviewExporter.generate_docx(state.summary.model_dump(), history_list)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"Interview_Report_{session_id}.docx"
    else:
        raise HTTPException(status_code=400, detail="Invalid export format. Use 'pdf' or 'docx'.")

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
