"""
AttentionX — AI Service (Phase 3: Fully Implemented)
=====================================================
Handles all interactions with:
  - Faster-Whisper  → Speech-to-text transcription (WhisperModel singleton via lru_cache)
  - Google Gemini 2.5 Flash → Narrative arc extraction with viral scoring
"""

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class TranscriptSegment:
    """A single segment from Whisper output."""
    start: float        # seconds
    end: float          # seconds
    text: str
    confidence: float = 1.0


@dataclass
class GoldenNugget:
    """
    A candidate viral clip identified by Gemini's narrative arc analysis.
    Spec-aligned dataclass: start, end, headline, rationale, viral_score.
    """
    start: float            # seconds
    end: float              # seconds
    headline: str           # punchy viral headline (<10 words)
    rationale: str          # 1-2 sentences why it will go viral
    viral_score: int        # 1-10 — hook strength score from Gemini
    duration: float         # computed: end - start
    transcript_snippet: str = ""

    def __post_init__(self):
        # Enforce 60s cap — safety net even if Gemini ignores the constraint
        if self.duration > 60.0:
            self.end = self.start + 60.0
            self.duration = 60.0
        # Clamp viral_score to 1-10
        self.viral_score = max(1, min(10, int(self.viral_score)))


# ---------------------------------------------------------------------------
# Whisper Model Singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_whisper_model(model_size: str, device: str, compute_type: str):
    """
    Load and cache the WhisperModel as a singleton.

    Using @lru_cache(maxsize=1) ensures the heavy model (200MB–3GB) is loaded
    exactly ONCE per process lifetime — regardless of how many times
    /analyze is called.

    Args:
        model_size:    'base', 'small', 'medium', 'large-v3-turbo', etc.
        device:        'cpu' or 'cuda'
        compute_type:  'int8' (CPU-optimal), 'float16' (GPU-optimal)

    Returns:
        Loaded faster_whisper.WhisperModel instance.
    """
    from faster_whisper import WhisperModel
    logger.info(
        f"Loading WhisperModel '{model_size}' on {device} "
        f"[compute_type={compute_type}] — this may take 30–60 seconds..."
    )
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    logger.info(f"WhisperModel '{model_size}' loaded and cached ✓")
    return model


# ---------------------------------------------------------------------------
# Transcription Service
# ---------------------------------------------------------------------------

class TranscriptionService:
    """
    Wraps faster-whisper for speech-to-text transcription.
    The WhisperModel is cached as a singleton to avoid repeated RAM loads.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
    ):
        self.model_size = model_size
        self.device = device
        # int8 quantisation: 2× faster on CPU, negligible accuracy loss
        self.compute_type = "int8" if device == "cpu" else "float16"

    def transcribe(self, audio_path: str) -> list[TranscriptSegment]:
        """
        Transcribe an audio file and return a list of timestamped segments.

        This is a SYNCHRONOUS blocking call — invoke via asyncio.to_thread()
        from async FastAPI endpoints.

        Args:
            audio_path: Path to .wav, .mp3, or .mp4 file.
                        Use extract_audio() first for best results (16kHz mono WAV).

        Returns:
            List[TranscriptSegment] with precise start/end/text per segment.
        """
        model = _get_whisper_model(self.model_size, self.device, self.compute_type)
        logger.info(f"Transcribing: {audio_path}")

        try:
            result_tuple = model.transcribe(
                audio_path,
                beam_size=5,
                word_timestamps=False,
                vad_filter=True,          # Voice Activity Detection — skips silence
                vad_parameters={"min_silence_duration_ms": 500},
            )
            # faster-whisper returns (segments_generator, TranscriptionInfo)
            if isinstance(result_tuple, tuple) and len(result_tuple) == 2:
                segments_gen, info = result_tuple
            else:
                raise RuntimeError("Unexpected return value from WhisperModel.transcribe()")
        except Exception as exc:
            raise RuntimeError(f"Whisper model error: {exc}") from exc

        # Materialise the lazy generator into a list
        result: list[TranscriptSegment] = []
        try:
            for seg in segments_gen:
                result.append(TranscriptSegment(
                    start=round(seg.start, 2),
                    end=round(seg.end, 2),
                    text=seg.text.strip(),
                    confidence=round(getattr(seg, "avg_logprob", 0.0), 3),
                ))
        except Exception as exc:
            logger.warning(f"Segment materialisation error: {exc} — returning partial result")

        logger.info(
            f"Transcription complete: {len(result)} segments, "
            f"detected language={getattr(info, 'language', '?')} "
            f"({getattr(info, 'language_probability', 0):.0%})"
        )
        return result



# ---------------------------------------------------------------------------
# Transcript Formatting
# ---------------------------------------------------------------------------

def _fmt_time(seconds: float) -> str:
    """Format seconds as H:MM:SS."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h}:{m:02d}:{s:02d}"


def _format_transcript_for_gemini(segments: list[TranscriptSegment]) -> str:
    """
    Convert segment list to a human-readable timestamped transcript.

    Format:
        [0:00:12 → 0:00:45] The biggest mistake founders make is hiring too early...
        [0:00:45 → 0:01:23] When you hire before product-market fit...

    This format lets Gemini reason about narrative arcs across time boundaries.
    """
    lines = [
        f"[{_fmt_time(seg.start)} → {_fmt_time(seg.end)}] {seg.text}"
        for seg in segments
        if seg.text.strip()
    ]
    return "\n".join(lines)


def _get_transcript_snippet(
    segments: list[TranscriptSegment],
    start: float,
    end: float,
) -> str:
    """Extract the raw transcript text covering [start, end] seconds."""
    relevant = [
        seg.text for seg in segments
        if seg.start >= start - 2 and seg.end <= end + 2
    ]
    snippet = " ".join(relevant).strip()
    return snippet[:400] + "…" if len(snippet) > 400 else snippet


# ---------------------------------------------------------------------------
# Gemini Narrative Analysis Service
# ---------------------------------------------------------------------------

_GEMINI_PROMPT_TEMPLATE = """\
You are AttentionX, an elite viral content strategist.

Analyse this video transcript and identify exactly {n_clips} clips that will perform \
best as viral short-form content (Reels / TikTok / Shorts).

Each clip MUST contain all three elements:
  1. VIRAL HOOK   — an opening line that stops the scroll instantly
  2. STORY ARC    — rising tension, conflict, or a curiosity gap that keeps viewers watching
  3. PAYOFF       — a satisfying resolution, insight, or surprising twist

Hard constraints:
  - Each clip must be AT MOST 60 seconds long  (end - start <= 60.0)
  - Clips must NOT overlap with each other
  - start and end values are in SECONDS from the beginning of the video
  - Prioritise emotional resonance and genuine insight over mere volume or excitement
  - viral_score must reflect the HOOK strength specifically (1 = weak, 10 = irresistible)

VIDEO TRANSCRIPT:
{transcript}

Return ONLY a valid JSON array with exactly {n_clips} objects — no extra text, no markdown:
[
  {{
    "start": <float, seconds>,
    "end": <float, seconds>,
    "headline": "<punchy viral headline, under 10 words>",
    "rationale": "<1-2 sentences — exactly WHY this specific clip will go viral>",
    "viral_score": <integer 1-10>
  }}
]
"""


class NarrativeAnalysisService:
    """
    Uses Gemini 2.5 Flash to identify narrative story arcs in a transcript.
    response_mime_type="application/json" forces clean parseable output.
    """

    def __init__(self, api_key: str, model_id: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_id = model_id

    def extract_golden_nuggets(
        self,
        segments: list[TranscriptSegment],
        max_clips: int = 3,
    ) -> list[GoldenNugget]:
        """
        Send the formatted transcript to Gemini and return GoldenNugget list.

        This is a SYNCHRONOUS blocking call — invoke via asyncio.to_thread().

        Args:
            segments:  Whisper transcription output.
            max_clips: Number of clips to identify (default 3).

        Returns:
            List of GoldenNugget sorted by viral_score descending.

        Raises:
            ValueError: If API key is missing or Gemini returns malformed JSON.
            RuntimeError: On Gemini API errors.
        """
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file and restart the API."
            )

        if not segments:
            raise ValueError("Transcript is empty — cannot analyse a silent video.")

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        formatted = _format_transcript_for_gemini(segments)
        prompt = _GEMINI_PROMPT_TEMPLATE.format(
            n_clips=max_clips,
            transcript=formatted,
        )

        logger.info(
            f"Sending {len(segments)} segments to Gemini {self.model_id} "
            f"(requesting {max_clips} clips)..."
        )

        try:
            response = client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",  # Forces raw JSON output
                    temperature=0.4,    # Low = consistent, structured JSON
                    max_output_tokens=8192,  # Increased from 2048 to prevent JSON truncation
                )
            )
            raw_json = response.text
        except Exception as exc:
            raise RuntimeError(f"Gemini API error: {exc}") from exc

        # Parse and validate the JSON
        try:
            clips_raw: list[dict] = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.error(f"Gemini returned invalid JSON:\n{raw_json[:500]}")
            raise ValueError(f"Gemini returned malformed JSON: {exc}") from exc

        if not isinstance(clips_raw, list):
            raise ValueError(f"Expected JSON array, got {type(clips_raw).__name__}")

        nuggets: list[GoldenNugget] = []
        for item in clips_raw:
            try:
                start = float(item["start"])
                end = float(item["end"])
                duration = end - start

                nugget = GoldenNugget(
                    start=round(start, 2),
                    end=round(end, 2),
                    headline=str(item.get("headline", "Untitled Clip")),
                    rationale=str(item.get("rationale", "")),
                    viral_score=int(item.get("viral_score", 5)),
                    duration=round(duration, 2),
                    transcript_snippet=_get_transcript_snippet(segments, start, end),
                )
                nuggets.append(nugget)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(f"Skipping malformed clip entry {item}: {exc}")
                continue

        # Sort by viral_score descending
        nuggets.sort(key=lambda n: n.viral_score, reverse=True)

        logger.info(f"Gemini identified {len(nuggets)} golden nuggets ✓")
        return nuggets


# ---------------------------------------------------------------------------
# Orchestration: analyze_narrative_peaks()
# ---------------------------------------------------------------------------

def analyze_narrative_peaks(
    segments: list[TranscriptSegment],
    max_clips: int = 3,
) -> list[GoldenNugget]:
    """
    Convenience orchestrator: takes Whisper segments, returns GoldenNuggets.

    Reads GEMINI_API_KEY and GEMINI_MODEL_ID from environment.
    Designed to be called via asyncio.to_thread() from async endpoints.

    Args:
        segments:  Whisper output from TranscriptionService.transcribe().
        max_clips: How many golden nuggets to find.

    Returns:
        List of GoldenNugget sorted by viral_score descending.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    model_id = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash")

    service = NarrativeAnalysisService(api_key=api_key, model_id=model_id)
    return service.extract_golden_nuggets(segments, max_clips=max_clips)


# ---------------------------------------------------------------------------
# Convenience singleton factories
# ---------------------------------------------------------------------------

_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    global _transcription_service
    if _transcription_service is None:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        _transcription_service = TranscriptionService(
            model_size=model_size,
            device=device,
        )
    return _transcription_service
