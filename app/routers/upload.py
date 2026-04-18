"""
AttentionX — Upload Router
===========================
POST /api/v1/upload
  - Accepts .mp4 / .mov video files via multipart form upload
  - Verifies file content via magic bytes (no libmagic dependency)
  - Streams file to disk in 1 MB chunks (RAM-safe for files up to 2 GB+)
  - Extracts video metadata via MoviePy (non-blocking via asyncio.to_thread)
  - Returns a typed VideoUploadResponse with video_id and metadata
"""

import asyncio
import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.services.video_service import VideoMetadata, get_video_metadata

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1024 * 1024              # 1 MB — RAM-safe for any file size
OUTPUT_DIR = Path("output")
ALLOWED_EXTENSIONS = {".mp4", ".mov"}


# ---------------------------------------------------------------------------
# Magic-Byte MIME Verification
# ---------------------------------------------------------------------------
# MP4 and MOV files both use the ISO Base Media File Format (ISOBMFF).
# Their signature is the 4-byte ASCII string "ftyp" at byte offset 4–7.
# This check requires NO external library (python-magic needs a C DLL on Windows).
#
# Additionally, QuickTime MOV files can start with "moov", "mdat", "wide",
# or "free" atoms — we accept those too.

_VALID_SIGNATURES: list[tuple[int, bytes]] = [
    (4, b"ftyp"),   # ISO Base Media: MP4, MOV (most common)
    (4, b"moov"),   # QuickTime legacy
    (4, b"mdat"),   # QuickTime legacy
    (4, b"wide"),   # QuickTime compatibility atom
    (4, b"free"),   # QuickTime skip atom
    (0, b"RIFF"),   # AVI / WAV — rejected below at extension check
]

def _verify_magic_bytes(header: bytes) -> bool:
    """
    Return True if the file header matches a known video container signature.
    Reads only the first 12 bytes — zero overhead for large files.
    """
    if len(header) < 8:
        return False
    for offset, sig in _VALID_SIGNATURES:
        if header[offset : offset + len(sig)] == sig:
            return True
    return False


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class VideoMetadataResponse(BaseModel):
    duration_seconds: float
    duration_formatted: str
    width: int
    height: int
    fps: float
    metadata_available: bool


class VideoUploadResponse(BaseModel):
    video_id: str
    original_filename: str
    file_path: str
    file_size_mb: float
    metadata: VideoMetadataResponse


def _metadata_to_response(meta: VideoMetadata) -> VideoMetadataResponse:
    return VideoMetadataResponse(
        duration_seconds=meta.duration_seconds,
        duration_formatted=meta.duration_formatted,
        width=meta.width,
        height=meta.height,
        fps=meta.fps,
        metadata_available=meta.metadata_available,
    )


# ---------------------------------------------------------------------------
# Upload Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=VideoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a video file for processing",
)
async def upload_video(file: UploadFile = File(...)) -> VideoUploadResponse:
    """
    Accepts a multipart .mp4 or .mov video upload.

    Processing steps:
      1. Validate file extension
      2. Read first 12 bytes → verify magic signature (ISOBMFF / QuickTime)
      3. Generate UUID video_id, create output/{video_id}/ with exist_ok=True
      4. Stream file to disk in 1 MB chunks (RAM usage is always ≤ 1 MB)
      5. Extract metadata via MoviePy in a thread pool (non-blocking)
      6. Return VideoUploadResponse with video_id, path, size, and metadata
    """

    # ── 1. Extension validation ──────────────────────────────────────────────
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file extension '{suffix}'. "
                f"Accepted: {', '.join(ALLOWED_EXTENSIONS)}"
            ),
        )

    # ── 2. Magic-byte MIME verification ─────────────────────────────────────
    header = await file.read(12)
    if not _verify_magic_bytes(header):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "File content does not match a valid video container "
                "(expected MP4 / MOV / QuickTime). "
                "The file may be corrupted or have a mismatched extension."
            ),
        )
    await file.seek(0)    # Reset stream to beginning before streaming to disk

    # ── 3. Create job directory ──────────────────────────────────────────────
    video_id = str(uuid.uuid4())
    job_dir = OUTPUT_DIR / video_id
    job_dir.mkdir(parents=True, exist_ok=True)   # exist_ok prevents race conditions
    dest_path = job_dir / f"source{suffix}"

    logger.info(f"[{video_id}] Receiving '{original_name}' → {dest_path}")

    # ── 4. Stream file to disk in 1 MB chunks ───────────────────────────────
    total_bytes = 0
    try:
        async with aiofiles.open(dest_path, "wb") as out_file:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                await out_file.write(chunk)
                total_bytes += len(chunk)
    except OSError as exc:
        logger.error(f"[{video_id}] Disk write failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save video to disk: {exc}",
        )
    finally:
        await file.close()

    file_size_mb = total_bytes / 1_000_000
    logger.info(f"[{video_id}] Saved {file_size_mb:.1f} MB to {dest_path}")

    # ── 5. Extract metadata (non-blocking thread pool) ───────────────────────
    logger.info(f"[{video_id}] Extracting video metadata...")
    metadata: VideoMetadata = await asyncio.to_thread(
        get_video_metadata, str(dest_path)
    )

    if metadata.metadata_available:
        logger.info(
            f"[{video_id}] Metadata: {metadata.duration_formatted}, "
            f"{metadata.width}×{metadata.height} @ {metadata.fps:.2f}fps"
        )
    else:
        logger.warning(f"[{video_id}] Metadata extraction failed — continuing with defaults")

    # ── 6. Return response ───────────────────────────────────────────────────
    return VideoUploadResponse(
        video_id=video_id,
        original_filename=original_name,
        file_path=str(dest_path),
        file_size_mb=round(file_size_mb, 2),
        metadata=_metadata_to_response(metadata),
    )
