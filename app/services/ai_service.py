"""
AttentionX — AI Service
=======================
Handles all interactions with:
  - Google Gemini 2.5 Flash  → Narrative arc extraction (Hook → Agitation → Solution)
  - Faster-Whisper v3 Turbo  → Speech-to-text transcription

Stubs implemented here; full logic arrives in Prompt #3.
"""

import logging
from dataclasses import dataclass, field
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
class NarrativeClip:
    """A candidate clip identified by Gemini's narrative arc analysis."""
    start: float                        # seconds
    end: float                          # seconds
    hook: str                           # opening line / hook
    agitation: str                      # problem being raised
    solution: str                       # resolution / insight
    virality_score: float               # 0.0 – 1.0 (Gemini's confidence)
    transcript_snippet: str = ""
    audio_spike_score: float = 0.0      # injected later by audio service
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transcription Service
# ---------------------------------------------------------------------------

class TranscriptionService:
    """
    Wraps faster-whisper for speech-to-text transcription.
    Model: 'large-v3-turbo' for best accuracy/speed tradeoff.
    """

    def __init__(self, model_size: str = "large-v3-turbo", device: str = "cpu"):
        self.model_size = model_size
        self.device = device
        self._model = None  # lazy-loaded on first call

    def _load_model(self):
        """Lazy-load the Whisper model to avoid cold-start penalties at import."""
        if self._model is None:
            logger.info(f"Loading Whisper model '{self.model_size}' on {self.device}...")
            # TODO (Prompt #3): from faster_whisper import WhisperModel
            # self._model = WhisperModel(self.model_size, device=self.device)
            logger.info("Whisper model loaded ✓")

    def transcribe(self, audio_path: str) -> list[TranscriptSegment]:
        """
        Transcribe an audio/video file and return timestamped segments.

        Args:
            audio_path: Path to .wav / .mp4 file.

        Returns:
            List of TranscriptSegment with start, end, text, confidence.

        TODO (Prompt #3): Replace stub with real faster-whisper call.
        """
        self._load_model()
        logger.info(f"Transcribing: {audio_path}")

        # --- STUB ---
        return [
            TranscriptSegment(start=0.0, end=5.0, text="[Transcription stub — Prompt #3]")
        ]


# ---------------------------------------------------------------------------
# Gemini Narrative Analysis Service
# ---------------------------------------------------------------------------

class NarrativeAnalysisService:
    """
    Uses Gemini 2.5 Flash to identify narrative story arcs in a transcript.
    Looks for segments with a clear Hook → Agitation → Solution structure.
    """

    SYSTEM_PROMPT = """You are an expert viral content strategist and editor.
Your task is to analyse a video transcript and identify the most compelling
60-second segments that follow a Hook → Agitation → Solution narrative arc.

For each clip candidate, provide:
- start_time (seconds)
- end_time (seconds, max 60s after start)
- hook (the attention-grabbing opening statement)
- agitation (the problem or tension being raised)
- solution (the insight, advice, or resolution)
- virality_score (float 0.0–1.0, your confidence this will go viral)
- tags (list of content tags, e.g. ["mindset", "productivity"])

Return your response as a valid JSON array of clip objects.
Prioritise emotional resonance and genuine insight over mere volume or excitement.
"""

    def __init__(self, api_key: str, model_id: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_id = model_id
        self._client = None  # lazy-loaded

    def _get_client(self):
        """Lazy-initialise the Gemini client."""
        if self._client is None:
            logger.info(f"Initialising Gemini client (model: {self.model_id})...")
            # TODO (Prompt #3):
            # import google.generativeai as genai
            # genai.configure(api_key=self.api_key)
            # self._client = genai.GenerativeModel(self.model_id)
        return self._client

    def extract_narrative_clips(
        self,
        transcript_segments: list[TranscriptSegment],
        max_clips: int = 5,
    ) -> list[NarrativeClip]:
        """
        Send the full transcript to Gemini and return ranked NarrativeClip list.

        Args:
            transcript_segments: Whisper output segments.
            max_clips: Maximum number of clips to return.

        Returns:
            List of NarrativeClip sorted by virality_score descending.

        TODO (Prompt #3): Replace stub with real Gemini API call + JSON parse.
        """
        self._get_client()
        logger.info(f"Sending transcript to Gemini ({len(transcript_segments)} segments)...")

        # --- STUB ---
        return [
            NarrativeClip(
                start=0.0,
                end=60.0,
                hook="[Hook stub]",
                agitation="[Agitation stub]",
                solution="[Solution stub]",
                virality_score=0.95,
                transcript_snippet="[Transcript snippet stub — Prompt #3]",
                tags=["stub"],
            )
        ]


# ---------------------------------------------------------------------------
# Convenience singleton factory
# ---------------------------------------------------------------------------

_transcription_service: Optional[TranscriptionService] = None
_narrative_service: Optional[NarrativeAnalysisService] = None


def get_transcription_service() -> TranscriptionService:
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service


def get_narrative_service(api_key: str, model_id: str = "gemini-2.5-flash") -> NarrativeAnalysisService:
    global _narrative_service
    if _narrative_service is None:
        _narrative_service = NarrativeAnalysisService(api_key=api_key, model_id=model_id)
    return _narrative_service
