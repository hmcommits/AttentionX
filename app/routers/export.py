"""
AttentionX — Export Router (Phase 4: Vision Engine)
====================================================
POST /api/v1/export/{video_id}/{nugget_index}
    Renders a 9:16 vertical clip for a specific Golden Nugget.
    Returns clip_url pointing to the download endpoint.
    Idempotent: re-calling returns the cached clip instantly.

GET  /api/v1/clips/{video_id}/{filename}
    Streams a rendered clip file back to the browser / Streamlit.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.video_service import render_clip, RenderedClip

logger = logging.getLogger(__name__)

router = APIRouter()

OUTPUT_DIR = Path("output")
API_BASE   = "http://localhost:8000"
SOURCE_EXTENSIONS = [".mp4", ".mov"]



# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class ExportResponse(BaseModel):
    video_id:      str
    nugget_index:  int
    clip_path:     str
    clip_url:      str           # streamable URL served by GET /clips/...
    duration:      float
    width:         int
    height:        int
    face_tracked:  bool
    cached:        bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_source_file(job_dir: Path) -> Optional[Path]:
    for ext in SOURCE_EXTENSIONS:
        candidate = job_dir / f"source{ext}"
        if candidate.exists():
            return candidate
    return None


def _load_json(path: Path) -> Optional[dict | list]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Failed to read {path}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Download Endpoint (must come first for router registration order)
# ---------------------------------------------------------------------------

@router.get(
    "/clips/{video_id}/{filename}",
    summary="Stream a rendered vertical clip",
)
async def serve_clip(video_id: str, filename: str) -> FileResponse:
    """
    Stream a rendered .mp4 clip file to the browser.
    Used by Streamlit's st.video() and st.download_button().
    """
    clip_path = OUTPUT_DIR / video_id / filename

    if not clip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Clip '{filename}' not found for video_id '{video_id}'.",
        )

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=filename,
        headers={"Accept-Ranges": "bytes"},   # enables video seeking in browser
    )


# ---------------------------------------------------------------------------
# Export Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/export/{video_id}/{nugget_index}",
    response_model=ExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Render a 9:16 vertical clip for a specific Golden Nugget",
)
async def export_clip(
    video_id:     str,
    nugget_index: int,
) -> ExportResponse:
    """
    Renders a 9:16 vertical clip for nugget at position `nugget_index` in
    `analysis.json`. The clip includes:
      - Smart face-tracked crop (MediaPipe, falls back to centre crop)
      - Glassmorphic headline overlay at the top
      - Karaoke-style time-synced captions at the bottom

    Idempotent: if `clip_{index:02d}.mp4` already exists, returns it
    immediately without re-rendering. This allows safe re-clicks in Streamlit.

    POST /api/v1/export/{video_id}/{nugget_index}
    """

    # ── 1. Validate job directory ────────────────────────────────────────────
    job_dir = OUTPUT_DIR / video_id
    if not job_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No job found for video_id '{video_id}'. Upload + analyze first.",
        )

    # ── 2. Load analysis.json ─────────────────────────────────────────────────
    analysis = _load_json(job_dir / "analysis.json")
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="analysis.json not found. Run POST /analyze/{video_id} first.",
        )

    nuggets = analysis.get("golden_nuggets", [])
    if nugget_index < 0 or nugget_index >= len(nuggets):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nugget index {nugget_index} not found (only {len(nuggets)} nuggets).",
        )

    nugget = nuggets[nugget_index]
    clip_filename = f"clip_{nugget_index:02d}.mp4"
    clip_path     = job_dir / clip_filename
    clip_url      = f"{API_BASE}/api/v1/clips/{video_id}/{clip_filename}"

    # ── 3. Cache hit — return immediately ────────────────────────────────────
    if clip_path.exists():
        logger.info(f"[{video_id}] Returning cached clip: {clip_filename}")
        return ExportResponse(
            video_id=video_id,
            nugget_index=nugget_index,
            clip_path=str(clip_path),
            clip_url=clip_url,
            duration=nugget.get("duration", 0.0),
            width=0,
            height=0,
            face_tracked=False,
            cached=True,
        )

    # ── 4. Find source video ──────────────────────────────────────────────────
    source_path = _find_source_file(job_dir)
    if source_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source video file not found in job directory.",
        )

    # ── 5. Load transcript segments for karaoke captions ─────────────────────
    transcript_raw = _load_json(job_dir / "transcript.json")
    transcript_segments: list[dict] = transcript_raw if isinstance(transcript_raw, list) else []
    logger.info(
        f"[{video_id}] Transcript segments loaded: {len(transcript_segments)} total"
    )

    # ── 6. Render ─────────────────────────────────────────────────────────────
    logger.info(
        f"[{video_id}] Rendering nugget #{nugget_index}: "
        f"[{nugget['start']:.1f}s → {nugget['end']:.1f}s] '{nugget['headline']}'"
    )

    try:
        rendered: RenderedClip = await asyncio.to_thread(
            render_clip,
            str(source_path),               # source_path
            str(job_dir),                   # job_dir
            float(nugget["start"]),         # start
            float(nugget["end"]),           # end
            str(nugget["headline"]),        # headline
            nugget_index,                   # nugget_index
            transcript_segments,            # transcript_segments
            True,                           # face_track
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    logger.info(
        f"[{video_id}] Render complete: {clip_filename} "
        f"{rendered.width}×{rendered.height}, "
        f"face_tracked={rendered.face_tracked}"
    )

    return ExportResponse(
        video_id=video_id,
        nugget_index=nugget_index,
        clip_path=str(clip_path),
        clip_url=clip_url,
        duration=rendered.duration,
        width=rendered.width,
        height=rendered.height,
        face_tracked=rendered.face_tracked,
        cached=False,
    )
