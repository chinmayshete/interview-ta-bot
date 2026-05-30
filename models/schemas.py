"""
Pydantic models for request / response schemas and interview state.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Category(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    SYSTEM_DESIGN = "system_design"
    RESUME_BASED = "resume_based"


class Rating(str, Enum):
    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"


class RiskFlag(str, Enum):
    NONE = "none"
    RESUME_MISMATCH = "resume_mismatch"
    SHALLOW_KNOWLEDGE = "shallow_knowledge"
    OVERCLAIMING = "overclaiming"


# ── Sub-models for the AI response ──────────────────────────────────────────

class NextQuestion(BaseModel):
    question: str
    difficulty: Difficulty
    category: Category


class Evaluation(BaseModel):
    candidate_answer_summary: str
    rating: Rating
    confidence_score: int = Field(ge=0, le=100)
    reasoning: str


class FollowUp(BaseModel):
    should_ask: bool
    question: Optional[str] = None


class InterviewGuidance(BaseModel):
    suggestion_to_interviewer: str
    risk_flag: RiskFlag


class InterviewSummary(BaseModel):
    """The final performance summary of the candidate."""
    overall_score: int = Field(ge=0, le=100)
    overall_rating: str
    summary_statement: str
    strengths: list[str]
    weaknesses: list[str]
    technical_proficiency: str
    behavioral_fit: str
    key_topics_covered: list[str]
    recommendation: str


# ── Main AI response schema ─────────────────────────────────────────────────

class InterviewResponse(BaseModel):
    """The strict JSON structure returned by the AI engine on each turn."""
    next_question: NextQuestion
    expected_answer: str
    reference_answer: str
    evaluation: Evaluation
    follow_up: FollowUp
    interview_guidance: InterviewGuidance


# ── Interview state (persisted per session) ─────────────────────────────────

class HistoryEntry(BaseModel):
    question: str
    answer: str
    rating: Rating
    difficulty: Difficulty
    category: Category


class InterviewState(BaseModel):
    """Tracks the evolving state of a single interview session."""
    session_id: str = ""
    resume_text: str = ""
    jd_text: str = ""
    question_count: int = 0
    current_difficulty: Difficulty = Difficulty.EASY
    topics_covered: list[str] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)
    consecutive_weak: int = 0
    consecutive_strong: int = 0
    is_active: bool = False
    summary: Optional[InterviewSummary] = None


# ── API request models ──────────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    resume_text: str
    jd_text: str


class InterviewTurnRequest(BaseModel):
    session_id: str
    candidate_answer: str


class TranscriptionResponse(BaseModel):
    text: str
    session_id: str
