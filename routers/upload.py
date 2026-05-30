"""
Upload routes — handle resume and JD file uploads.
"""

import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from services.resume_parser import parse_resume

import tempfile

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload a resume file (PDF or DOCX) and return extracted text.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Upload a .pdf or .docx file.",
        )

    # Save to a system temp location to prevent Live Server from refreshing the page
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = parse_resume(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {exc}")
    finally:
        # Clean up uploaded file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"filename": file.filename, "text": text, "char_count": len(text)}


@router.post("/jd")
async def upload_jd(jd_text: str = Form(...)):
    """
    Accept a Job Description as plain text.
    """
    if len(jd_text.strip()) < 20:
        raise HTTPException(
            status_code=400,
            detail="Job description is too short. Provide a meaningful JD.",
        )
    return {"text": jd_text.strip(), "char_count": len(jd_text.strip())}
