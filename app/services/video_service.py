"""
AttentionX — Video Service
==========================
Handles all video processing:
  - MoviePy ≥ 2.1.1  → Clip trimming, encoding, compositing
  - MediaPipe         → Face detection & tracking for smart 9:16 cropping
  - Librosa           → Audio spike detection (secondary virality signal)

Phase 2 additions:
  - VideoMetadata dataclass
  - get_video_metadata() — safe extraction with try/finally resource cleanup
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class VideoMetadata:
    """
    Metadata extracted from a source video file by MoviePy.
    If extraction fails, metadata_available=False and all numeric fields are 0.
    """
    duration_seconds: float
    duration_formatted: str    # "H:MM:SS"
    width: int
    height: int
    fps: float
    metadata_available: bool = True


@dataclass
class AudioSpike:
    """A detected audio energy spike — secondary virality signal."""
    timestamp: float    # seconds
    energy: float       # RMS energy normalised 0.0–1.0
    duration: float     # seconds around the spike


@dataclass
class RenderedClip:
    """Result of the video rendering pipeline."""
    job_id: str
    clip_index: int
    output_path: str
    duration: float     # seconds
    width: int
    height: int
    face_tracked: bool  # whether MediaPipe successfully tracked a face


# ---------------------------------------------------------------------------
# Helper: Format seconds → H:MM:SS
# ---------------------------------------------------------------------------

def _format_duration(seconds: float) -> str:
    """Convert a float number of seconds to a human-readable H:MM:SS string."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Metadata Extraction
# ---------------------------------------------------------------------------

def get_video_metadata(file_path: str) -> VideoMetadata:
    """
    Extract duration, resolution, and FPS from a video file using MoviePy.

    Design decisions:
      - Uses a strict try/finally block to ensure clip.close() is ALWAYS
        called — prevents file handle leaks on Windows and Linux.
      - If MoviePy fails for any reason (corruption, unsupported codec,
        missing ffmpeg), catches the exception and returns a clean
        VideoMetadata with metadata_available=False instead of crashing.
      - This function is SYNCHRONOUS — call it via asyncio.to_thread()
        from async FastAPI endpoints to avoid blocking the event loop.

    Args:
        file_path: Absolute or relative path to the video file.

    Returns:
        VideoMetadata populated with real values, or a safe "unavailable"
        stub if extraction fails.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"get_video_metadata: file not found → {file_path}")
        return _unavailable_metadata()

    clip = None
    try:
        from moviepy import VideoFileClip

        logger.info(f"Opening VideoFileClip: {file_path}")
        # audio=False skips audio decoding — faster for metadata-only extraction
        clip = VideoFileClip(str(path), audio=False)

        duration_secs = float(clip.duration or 0.0)
        width, height = clip.size          # returns (width, height) tuple
        fps = float(clip.fps or 0.0)

        return VideoMetadata(
            duration_seconds=round(duration_secs, 2),
            duration_formatted=_format_duration(duration_secs),
            width=int(width),
            height=int(height),
            fps=round(fps, 2),
            metadata_available=True,
        )

    except FileNotFoundError:
        logger.error(f"get_video_metadata: FileNotFoundError → {file_path}")
        return _unavailable_metadata()

    except Exception as exc:
        # Catches: corrupt files, missing codecs, ffmpeg errors, MoviePy bugs
        logger.warning(
            f"get_video_metadata: failed to read '{file_path}' — {type(exc).__name__}: {exc}"
        )
        return _unavailable_metadata()

    finally:
        # Always close the clip regardless of success or failure.
        # MoviePy 2.x requires explicit close() to release the ffmpeg reader.
        if clip is not None:
            try:
                clip.close()
                logger.debug(f"VideoFileClip closed: {file_path}")
            except Exception as close_exc:
                logger.debug(f"clip.close() raised (non-critical): {close_exc}")


def _unavailable_metadata() -> VideoMetadata:
    """Return a clean 'metadata unavailable' sentinel — never crashes the caller."""
    return VideoMetadata(
        duration_seconds=0.0,
        duration_formatted="Unknown",
        width=0,
        height=0,
        fps=0.0,
        metadata_available=False,
    )


# ---------------------------------------------------------------------------
# Audio Analysis Service
# ---------------------------------------------------------------------------

class AudioSpikeService:
    """
    Uses Librosa to detect high-energy moments in the audio track.
    These timestamps are fused with Gemini's narrative scores for final ranking.
    """

    def __init__(self, energy_threshold: float = 0.75):
        """
        Args:
            energy_threshold: Minimum normalised RMS energy (0–1) to count as a spike.
        """
        self.energy_threshold = energy_threshold

    def detect_spikes(self, audio_path: str) -> list[AudioSpike]:
        """
        Load audio with Librosa and find high-energy timestamps.

        Args:
            audio_path: Path to .wav or .mp4 file.

        Returns:
            List of AudioSpike sorted by timestamp.

        TODO (Prompt #4): Replace stub with real librosa.load + RMS analysis.
        """
        logger.info(f"Detecting audio spikes in: {audio_path}")

        # --- STUB ---
        return [
            AudioSpike(timestamp=12.5, energy=0.91, duration=3.0),
            AudioSpike(timestamp=47.0, energy=0.88, duration=2.5),
        ]


# ---------------------------------------------------------------------------
# Face Tracking Service
# ---------------------------------------------------------------------------

class FaceTrackingService:
    """
    Uses MediaPipe Face Detection to keep the speaker centred in 9:16 crops.
    For each frame: detect face bounding box → compute crop centre → apply crop.
    Uses a smoothing window to avoid jitter between frames.
    """

    TARGET_ASPECT = (9, 16)
    SMOOTHING_WINDOW = 15   # frames — smooths the crop centre over time

    def __init__(self):
        self._detector = None   # lazy-loaded

    def _load_detector(self):
        """Lazy-load MediaPipe face detector."""
        if self._detector is None:
            logger.info("Loading MediaPipe face detector...")
            # TODO (Prompt #4):
            # import mediapipe as mp
            # self._detector = mp.solutions.face_detection.FaceDetection(
            #     model_selection=1, min_detection_confidence=0.5
            # )
            logger.info("MediaPipe face detector loaded ✓")

    def compute_crop_box(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        """
        Compute the 9:16 crop box centred on the detected face.

        Returns:
            (x1, y1, x2, y2) pixel coordinates.

        TODO (Prompt #4): Replace stub with real per-frame detection + smoothing.
        """
        self._load_detector()

        # --- STUB: centre crop ---
        target_width = int(frame_height * 9 / 16)
        x1 = (frame_width - target_width) // 2
        return (x1, 0, x1 + target_width, frame_height)


# ---------------------------------------------------------------------------
# Clip Rendering Service
# ---------------------------------------------------------------------------

class ClipRenderingService:
    """
    Orchestrates the full rendering pipeline:
      1. Trim source video to [start, end]
      2. Apply MediaPipe face-tracked 9:16 crop per frame
      3. Encode to H.264 + AAC with MoviePy ≥ 2.1.1
      4. Save to output/{job_id}/clip_{index}.mp4
    """

    def __init__(
        self,
        output_dir: str = "./output",
        face_tracking_service: Optional[FaceTrackingService] = None,
    ):
        self.output_dir = Path(output_dir)
        self.face_tracker = face_tracking_service or FaceTrackingService()

    def render_clip(
        self,
        source_path: str,
        job_id: str,
        clip_index: int,
        start: float,
        end: float,
    ) -> RenderedClip:
        """
        Trim and render a single clip with face-tracked 9:16 crop.

        Args:
            source_path: Path to the original uploaded video.
            job_id:      Unique job identifier (used for output directory).
            clip_index:  Clip sequence number (0-based).
            start:       Clip start time in seconds.
            end:         Clip end time in seconds (max start + 60).

        Returns:
            RenderedClip with output path and metadata.

        TODO (Prompt #4): Replace stub with full MoviePy + MediaPipe pipeline.
        """
        clip_output_dir = self.output_dir / job_id
        clip_output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(clip_output_dir / f"clip_{clip_index:02d}.mp4")

        logger.info(
            f"[{job_id}] Rendering clip {clip_index}: "
            f"{start:.1f}s → {end:.1f}s → {output_path}"
        )

        # --- STUB ---
        return RenderedClip(
            job_id=job_id,
            clip_index=clip_index,
            output_path=output_path,
            duration=end - start,
            width=1080,
            height=1920,
            face_tracked=False,  # True after Prompt #4
        )

    def render_all(
        self,
        source_path: str,
        job_id: str,
        segments: list[tuple[float, float]],
    ) -> list[RenderedClip]:
        """Render multiple clips sequentially."""
        return [
            self.render_clip(source_path, job_id, i, start, end)
            for i, (start, end) in enumerate(segments)
        ]


# ---------------------------------------------------------------------------
# Convenience singleton factories
# ---------------------------------------------------------------------------

_audio_service: Optional[AudioSpikeService] = None
_rendering_service: Optional[ClipRenderingService] = None


def get_audio_service() -> AudioSpikeService:
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioSpikeService()
    return _audio_service


def get_rendering_service(output_dir: str = "./output") -> ClipRenderingService:
    global _rendering_service
    if _rendering_service is None:
        _rendering_service = ClipRenderingService(output_dir=output_dir)
    return _rendering_service
