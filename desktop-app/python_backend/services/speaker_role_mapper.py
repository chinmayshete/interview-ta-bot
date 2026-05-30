"""
Speaker Role Mapper

Dynamically infers which Azure diarization label ("speaker_0", "speaker_1", ...)
maps to "interviewer" or "candidate".

Rules (NO hardcoding):
  - Interviewer: tends to ask questions (ends with "?"), shorter utterances, speaks first
  - Candidate: tends to give longer responses, follows the interviewer

Roles are re-evaluated on every utterance, so misclassifications self-correct
as more data accumulates.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

from models.live_schemas import LiveSessionState, Utterance


# Weight factors for role scoring
_QUESTION_MARK_WEIGHT   = 3     # "?" strongly implies interviewer
_SHORT_UTTERANCE_WEIGHT = 1     # short sentence implies interviewer
_LONG_UTTERANCE_WEIGHT  = 1     # long response implies candidate
_FIRST_SPEAKER_WEIGHT   = 2     # the first speaker is more likely the interviewer

SHORT_UTTERANCE_WORD_THRESHOLD = 20   # words
LONG_UTTERANCE_WORD_THRESHOLD  = 30   # words


def _word_count(text: str) -> int:
    return len(text.split())


def _has_question_mark(text: str) -> bool:
    return "?" in text


def _score_speaker(utterances: list[Utterance], speaker_label: str) -> float:
    """
    Compute an 'interviewer score' for a given speaker label.
    Higher score → more likely interviewer.
    """
    score = 0.0
    count = 0

    for u in utterances:
        if u.speaker_label != speaker_label:
            continue
        count += 1
        wc = _word_count(u.text)

        if _has_question_mark(u.text):
            score += _QUESTION_MARK_WEIGHT

        if wc <= SHORT_UTTERANCE_WORD_THRESHOLD:
            score += _SHORT_UTTERANCE_WEIGHT
        elif wc >= LONG_UTTERANCE_WORD_THRESHOLD:
            score -= _LONG_UTTERANCE_WEIGHT

    # Normalise by utterance count to avoid bias towards the more talkative speaker
    return score / max(count, 1)


def infer_roles(state: LiveSessionState) -> dict[str, str]:
    """
    Re-infer speaker → role mapping from the current transcript buffer.

    Returns updated speaker_roles dict  { "speaker_0": "interviewer", ... }
    Mutates state.speaker_roles in place and returns it.
    """
    if not state.transcript_buffer:
        return state.speaker_roles

    # Collect all unique speaker labels seen so far
    all_labels = list({u.speaker_label for u in state.transcript_buffer})

    if len(all_labels) == 1:
        # Only one speaker heard yet — assume interviewer until we hear more
        state.speaker_roles[all_labels[0]] = "interviewer"
        return state.speaker_roles

    # Score every speaker
    scores: dict[str, float] = {}
    for label in all_labels:
        scores[label] = _score_speaker(state.transcript_buffer, label)

    # Bonus: the very first speaker in the buffer gets +FIRST_SPEAKER_WEIGHT
    first_speaker = state.transcript_buffer[0].speaker_label
    if first_speaker in scores:
        scores[first_speaker] += _FIRST_SPEAKER_WEIGHT

    # Assign roles: top scorer = interviewer, rest = candidate
    sorted_speakers = sorted(scores.keys(), key=lambda lbl: scores[lbl], reverse=True)

    for i, label in enumerate(sorted_speakers):
        if i == 0:
            state.speaker_roles[label] = "interviewer"
        else:
            state.speaker_roles[label] = "candidate"

    return state.speaker_roles


def get_role(state: LiveSessionState, speaker_label: str) -> str:
    """
    Return the inferred role for a speaker label.
    Falls back to 'unknown' if not yet mapped.
    """
    return state.speaker_roles.get(speaker_label, "unknown")
