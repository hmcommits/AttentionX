"""
AttentionX — Analyze Router (Phase 3: Fully Implemented)
=========================================================
POST /api/v1/analyze/{video_id}

Pipeline:
  1. Validate job directory exists
  2. Return cached analysis.json if present (idempotent)
  3. Extract 16kHz mono WAV audio (via video_service.extract_audio)
  4. Transcribe with faster-whisper (via ai_service.TranscriptionService)
  5. Send transcript to Gemini 2.5 Flash (via ai_service.analyze_narrative_peaks)
  6. Persist results to output/{video_id}/analysis.json
  7. Return AnalysisResponse
"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.services.ai_service import (
    GoldenNugget,
    TranscriptSegment,
    analyze_narrative_peaks,
    get_transcription_service,
)
from app.services.video_service import extract_audio

logger = logging.getLogger(__name__)

router = APIRouter()

OUTPUT_DIR = Path("output")
SOURCE_EXTENSIONS = [".mp4", ".mov"]


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class GoldenNuggetResponse(BaseModel):
    start: float
    end: float
    headline: str
    rationale: str
    viral_score: int        # 1-10
    duration: float
    transcript_snippet: str


class AnalysisResponse(BaseModel):
    video_id: str
    transcript_segment_count: int
    golden_nuggets: list[GoldenNuggetResponse]
    cached: bool


def _nugget_to_response(n: GoldenNugget) -> GoldenNuggetResponse:
    return GoldenNuggetResponse(
        start=n.start,
        end=n.end,
        headline=n.headline,
        rationale=n.rationale,
        viral_score=n.viral_score,
        duration=n.duration,
        transcript_snippet=n.transcript_snippet,
    )


def _find_source_file(job_dir: Path) -> Path:
    """Locate source.mp4 or source.mov in the job directory."""
    for ext in SOURCE_EXTENSIONS:
        candidate = job_dir / f"source{ext}"
        if candidate.exists():
            return candidate
    return None


def _load_cached_analysis(job_dir: Path) -> dict | None:
    """
    Return the parsed analysis.json if it exists, else None.
    Enables idempotent endpoint behaviour — re-calling /analyze
    on the same video_id is instant and safe.
    """
    cache_path = job_dir / "analysis.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning(f"Corrupted analysis.json, will re-analyze: {exc}")
    return None


def _save_analysis(job_dir: Path, data: dict) -> None:
    """Persist analysis result to analysis.json."""
    cache_path = job_dir / "analysis.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Analysis saved → {cache_path}")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/analyze/{video_id}",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Whisper transcription + Gemini narrative arc analysis on an uploaded video",
)
async def analyze_video(
    video_id: str,
    max_clips: int = Query(
        default=3,
        ge=1,
        le=10,
        description="Number of golden nuggets to identify (wired to Streamlit slider)",
    ),
) -> AnalysisResponse:
    """
    Orchestrates the full AI analysis pipeline for a previously uploaded video.

    Steps:
      1. Validate video_id job directory
      2. Return cached result instantly if analysis.json exists
      3. Extract 16kHz mono WAV (optimised for Whisper)
      4. Transcribe with faster-whisper (WhisperModel singleton)
      5. Identify viral clips via Gemini 2.5 Flash (Hook → Arc → Payoff)
      6. Save analysis.json to output/{video_id}/
      7. Return AnalysisResponse with golden_nuggets
    """

    # ── 1. Validate job directory ────────────────────────────────────────────
    job_dir = OUTPUT_DIR / video_id
    if not job_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No job found for video_id '{video_id}'. Upload the video first.",
        )

    # ── 2. Cache check ───────────────────────────────────────────────────────
    cached = _load_cached_analysis(job_dir)
    if cached is not None:
        logger.info(f"[{video_id}] Returning cached analysis (analysis.json exists)")
        return AnalysisResponse(
            video_id=video_id,
            transcript_segment_count=cached.get("transcript_segment_count", 0),
            golden_nuggets=[
                GoldenNuggetResponse(**n) for n in cached.get("golden_nuggets", [])
            ],
            cached=True,
        )

    # ── 3. Find source video ─────────────────────────────────────────────────
    source_path = _find_source_file(job_dir)
    if source_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video not found in job directory '{video_id}'.",
        )

    logger.info(f"[{video_id}] Starting analysis pipeline for {source_path.name}")

    # ── 4. Extract 16kHz mono WAV ────────────────────────────────────────────
    try:
        logger.info(f"[{video_id}] Step 1/3: Extracting audio...")
        audio_path: str = await asyncio.to_thread(
            extract_audio, str(source_path), str(job_dir)
        )
    except (ValueError, RuntimeError) as exc:
        # Video has no audio — try transcribing the video directly as fallback
        logger.warning(f"[{video_id}] Audio extraction failed ({exc}), using source video directly")
        audio_path = str(source_path)

    # ── 5. Transcribe ────────────────────────────────────────────────────────
    try:
        logger.info(f"[{video_id}] Step 2/3: Transcribing with Whisper...")
        transcription_svc = get_transcription_service()
        segments: list[TranscriptSegment] = await asyncio.to_thread(
            transcription_svc.transcribe, audio_path
        )
    except Exception as exc:
        logger.error(f"[{video_id}] Transcription failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {exc}",
        )

    if not segments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No speech detected in the video. Cannot perform analysis.",
        )

    logger.info(f"[{video_id}] Transcription: {len(segments)} segments")

    # ── 6. Gemini narrative analysis ─────────────────────────────────────────
    try:
        logger.info(f"[{video_id}] Step 3/3: Gemini narrative analysis ({max_clips} clips)...")
        nuggets: list[GoldenNugget] = await asyncio.to_thread(
            analyze_narrative_peaks, segments, max_clips
        )
    except ValueError as exc:
        # Config or prompt errors (bad API key, empty transcript)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        # Gemini API error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    # ── 7. Build response + save cache ───────────────────────────────────────
    nugget_responses = [_nugget_to_response(n) for n in nuggets]

    result_dict = {
        "video_id": video_id,
        "transcript_segment_count": len(segments),
        "golden_nuggets": [nr.model_dump() for nr in nugget_responses],
        "cached": False,
    }

    try:
        _save_analysis(job_dir, result_dict)
    except Exception as exc:
        logger.warning(f"[{video_id}] Could not save analysis.json: {exc}")

    logger.info(
        f"[{video_id}] Analysis complete: {len(nuggets)} golden nuggets identified"
    )

    return AnalysisResponse(
        video_id=video_id,
        transcript_segment_count=len(segments),
        golden_nuggets=nugget_responses,
        cached=False,
    )
