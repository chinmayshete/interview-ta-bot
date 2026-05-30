"""
Interview engine — core AI logic that calls Azure OpenAI GPT-4.1
to evaluate answers and generate the next question.
"""

from __future__ import annotations

import json
import logging
from openai import AzureOpenAI
from config import get_settings
from prompts.interview_prompt import (
    SYSTEM_PROMPT,
    SUMMARY_PROMPT,
    SPELLING_CORRECTION_PROMPT,
    build_user_message,
    build_first_question_message,
    build_summary_user_message,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-initialised client
# ---------------------------------------------------------------------------
_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
    return _client


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _call_gpt(messages: list[dict], max_retries: int = 2) -> dict:
    """
    Send messages to GPT-4.1 and parse the JSON response.
    Retries up to `max_retries` times if the response is malformed JSON.
    """
    settings = get_settings()
    client = _get_client()

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.azure_gpt41_deployment,
                messages=messages,
                temperature=0.4,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content.strip()
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(
                "GPT returned malformed JSON (attempt %d/%d): %s",
                attempt + 1,
                max_retries + 1,
                content[:300] if 'content' in dir() else "N/A",
            )
            if attempt == max_retries:
                raise ValueError("GPT-4.1 failed to produce valid JSON after retries.")
        except Exception as exc:
            logger.error("Azure OpenAI call failed: %s", exc)
            raise


def generate_first_question(resume: str, jd: str) -> dict:
    """
    Generate the opening interview question.
    No prior Q&A exists — the model produces an initial evaluation stub.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_first_question_message(resume, jd)},
    ]
    return _call_gpt(messages)


def generate_next_turn(
    resume: str,
    jd: str,
    last_question: str,
    candidate_answer: str,
    interview_state: str,
) -> dict:
    """
    Evaluate the candidate's latest answer and return the next question
    along with evaluation, follow-up, and guidance — all as strict JSON.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_message(
                resume, jd, last_question, candidate_answer, interview_state,
            ),
        },
    ]
    return _call_gpt(messages)

def correct_text_spelling(raw_text: str) -> str:
    """
    Corrects spelling but explicitly avoids grammar correction or removing filler words.
    """
    settings = get_settings()
    client = _get_client()
    messages = [
        {"role": "system", "content": SPELLING_CORRECTION_PROMPT},
        {"role": "user", "content": raw_text},
    ]
    try:
        response = client.chat.completions.create(
            model=settings.azure_gpt41_deployment,
            messages=messages,
            temperature=0.0,
            max_tokens=1500,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Spell correction failed: %s", exc)
        # Fallback to returning raw text safely if there's any Azure error
        return raw_text

def generate_overall_summary(resume: str, jd: str, history: list) -> dict:
    """
    Analyze the full interview history and generate an overall performance summary.
    """
    messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": build_summary_user_message(resume, jd, history)},
    ]
    return _call_gpt(messages)
