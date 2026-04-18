"""
AttentionX — Video Service (Phase 4: Vision Engine)
====================================================
Handles all video processing:
  - extract_audio()       → 16kHz mono WAV for Whisper
  - get_video_metadata()  → duration/resolution/fps via MoviePy
  - render_clip()         → 9:16 crop + caption overlays + ultrafast encode
  - get_face_center()     → MediaPipe face detection (graceful degradation)
  - get_font_path()       → Windows font discovery with bitmap fallback
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MediaPipe availability (checked ONCE at module load)
# ---------------------------------------------------------------------------

_MEDIAPIPE_AVAILABLE: Optional[bool] = None


def _check_mediapipe() -> bool:
    """Lazy-check MediaPipe once per process. Caches result in module global."""
    global _MEDIAPIPE_AVAILABLE
    if _MEDIAPIPE_AVAILABLE is None:
        try:
            import mediapipe as mp  # noqa: F401
            _MEDIAPIPE_AVAILABLE = True
            logger.info("MediaPipe available ✓")
        except Exception as exc:
            _MEDIAPIPE_AVAILABLE = False
            logger.warning(
                f"MediaPipe unavailable — face-tracking disabled, using centre crop. "
                f"Reason: {exc}"
            )
    return _MEDIAPIPE_AVAILABLE


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
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Font Discovery (2026 Windows refinement)
# ---------------------------------------------------------------------------

def get_font_path(size: int = 36):
    """
    Discover the best available system font for caption rendering.

    Priority:
      1. Arial Bold (C:/Windows/Fonts/arialbd.ttf)  — clean, universally readable
      2. Segoe UI Bold (segoeuib.ttf)                — modern Windows default
      3. Calibri Bold (calibrib.ttf)                 — Office fallback
      4. PIL bitmap default                           — always works, any platform

    Returns:
        PIL.ImageFont.FreeTypeFont or PIL.ImageFont.ImageFont
    """
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",    # Arial Bold
        "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold
        "C:/Windows/Fonts/calibrib.ttf",   # Calibri Bold
        "C:/Windows/Fonts/arial.ttf",      # Arial Regular fallback
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                logger.debug(f"Font loaded: {path} @ {size}pt")
                return font
            except Exception:
                continue

    # Absolute fallback — always works on every platform
    logger.debug("Using PIL default bitmap font (no system font found)")
    try:
        return ImageFont.load_default(size=size)   # Pillow ≥ 10.1
    except TypeError:
        return ImageFont.load_default()             # older Pillow


# ---------------------------------------------------------------------------
# Text Utility
# ---------------------------------------------------------------------------

def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        test = " ".join(current + [word])
        try:
            bbox = draw.textbbox((0, 0), test, font=font)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w, _ = draw.textsize(test, font=font)

        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return lines if lines else [text[:60]]


# ---------------------------------------------------------------------------
# Caption Overlay Factories (PIL → numpy RGBA, NO ImageMagick)
# ---------------------------------------------------------------------------

def _draw_headline_overlay(w: int, h: int, text: str) -> np.ndarray:
    """
    Glassmorphic headline bar at the top of the frame.

    Design:
      - Semi-transparent black pill (alpha=160) — "glassmorphic" look
      - 24px margin from all three edges (left, right, top)
      - Rounded corners (radius=14)
      - White bold text, truncated to 45 chars
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 24
    font_size = max(22, min(34, h // 20))
    font = get_font_path(size=font_size)

    display = text[:45] + "…" if len(text) > 45 else text

    # Measure text
    try:
        bbox = draw.textbbox((0, 0), display, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(display, font=font)

    pad_x, pad_y = 18, 10
    bar_w = min(tw + pad_x * 2, w - margin * 2)
    bar_h = th + pad_y * 2

    # Centred horizontally with margin from top
    bar_x0 = (w - bar_w) // 2
    bar_y0 = margin
    bar_x1 = bar_x0 + bar_w
    bar_y1 = bar_y0 + bar_h

    # Semi-transparent rounded rectangle
    draw.rounded_rectangle(
        [bar_x0, bar_y0, bar_x1, bar_y1],
        radius=14,
        fill=(0, 0, 0, 160),
    )

    # White text centred in bar
    tx = bar_x0 + (bar_w - tw) // 2
    ty = bar_y0 + pad_y
    draw.text((tx, ty), display, fill=(255, 255, 255, 255), font=font)

    return np.array(img)   # (H, W, 4) uint8


def _draw_caption_overlay(w: int, h: int, text: str) -> np.ndarray:
    """
    Karaoke-style caption pill at the bottom of the frame.

    Design:
      - Dark semi-transparent rounded rectangle (alpha=180)
      - 20px margin from bottom (above phone chrome)
      - White text, word-wrapped to 80% of frame width
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = max(20, min(28, w // 22))
    font = get_font_path(size=font_size)

    max_text_w = int(w * 0.82)
    lines = _wrap_text(draw, text, font, max_text_w)
    line_h = font_size + 6
    total_text_h = len(lines) * line_h

    pad_x, pad_y = 16, 10
    pill_w = max_text_w + pad_x * 2
    pill_h = total_text_h + pad_y * 2

    margin_bottom = 40
    pill_x0 = (w - pill_w) // 2
    pill_y0 = h - pill_h - margin_bottom
    pill_x1 = pill_x0 + pill_w
    pill_y1 = pill_y0 + pill_h

    # Clamp to frame
    pill_y0 = max(0, pill_y0)

    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=10,
        fill=(0, 0, 0, 180),
    )

    y = pill_y0 + pad_y
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
        except AttributeError:
            lw, _ = draw.textsize(line, font=font)
        x = (w - lw) // 2
        draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
        y += line_h

    return np.array(img)   # (H, W, 4) uint8


# ---------------------------------------------------------------------------
# Face Detection & Smart Crop
# ---------------------------------------------------------------------------

def get_face_center(frame_rgb: np.ndarray, detector) -> Optional[int]:
    """
    Run MediaPipe on a single RGB frame and return the face centre X pixel.

    Returns:
        int — face centre X, or None if no face detected.
    """
    h, w = frame_rgb.shape[:2]
    results = detector.process(frame_rgb)
    if not results.detections:
        return None
    det = results.detections[0]
    bbox = det.location_data.relative_bounding_box
    face_cx = int((bbox.xmin + bbox.width / 2) * w)
    return max(0, min(face_cx, w - 1))


def sample_face_position(clip, n_samples: int = 5) -> tuple[int, bool]:
    """
    Sample N evenly-spaced frames from a clip, detect faces, return median X.

    Why N=5 samples?
      - A single frame may be a blink or partial occlusion.
      - 5 frames covers the temporal variance without per-frame overhead.
      - On a CPU, 5 × MediaPipe detections take ~0.3s — negligible.

    Returns:
        (face_cx: int, face_tracked: bool)
        face_cx      — median X of detected faces (or frame_w // 2 if none)
        face_tracked — True if a face was found in ≥ 1 frame
    """
    if not _check_mediapipe():
        return clip.w // 2, False

    import mediapipe as mp

    detector = None
    centers: list[int] = []
    try:
        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,              # long-range model (>2m)
            min_detection_confidence=0.4,   # generous threshold for variety of shots
        )

        times = np.linspace(0, max(0, clip.duration - 0.1), n_samples)
        for t in times:
            try:
                frame_bgr = clip.get_frame(t)
                # MoviePy frames are RGB; MediaPipe wants RGB
                frame_rgb = frame_bgr  # MoviePy is already RGB
                cx = get_face_center(frame_rgb, detector)
                if cx is not None:
                    centers.append(cx)
            except Exception as frame_exc:
                logger.debug(f"Frame {t:.1f}s detection error: {frame_exc}")
                continue

    finally:
        if detector is not None:
            try:
                detector.close()
            except Exception:
                pass

    if centers:
        return int(np.median(centers)), True
    else:
        logger.info("No face detected in sampled frames — using centre crop")
        return clip.w // 2, False


def compute_crop_box(frame_w: int, frame_h: int, face_cx: int) -> tuple[int, int, int, int]:
    """
    Compute a 9:16 crop box centred on the detected face.

    Crop math:
        crop_width = frame_height × (9/16)
        x1 = clamp(face_cx - crop_width/2, 0, frame_w - crop_width)

    Returns:
        (x1, y1, x2, y2) — pixel coordinates for MoviePy clip.cropped()
    """
    crop_w = int(frame_h * 9 / 16)
    
    # Ensure crop width is divisible by 2 for H.264 yuv420p support
    if crop_w % 2 != 0:
        crop_w -= 1
        
    x1 = face_cx - crop_w // 2
    # Clamp to frame bounds
    x1 = max(0, min(x1, frame_w - crop_w))
    
    # Ensure crop height is divisible by 2
    y2 = frame_h
    if y2 % 2 != 0:
        y2 -= 1
        
    return (x1, 0, x1 + crop_w, y2)


# ---------------------------------------------------------------------------
# Audio Extraction
# ---------------------------------------------------------------------------

def extract_audio(video_path: str, output_dir: Optional[str] = None) -> str:
    """
    Extract the audio track from a video file as a 16kHz mono WAV.

    Why 16kHz mono?
      - Whisper's native sample rate. Higher rates waste CPU on resampling.
      - Mono halves file size & transcription time vs stereo.

    Raises:
        FileNotFoundError: video_path does not exist.
        ValueError:        Video has no audio track.
        RuntimeError:      ffmpeg / MoviePy failure.
    """
    from moviepy import VideoFileClip

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    out_dir = Path(output_dir) if output_dir else video_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "audio.wav"

    logger.info(f"Extracting 16kHz mono WAV: {video_path} → {output_path}")

    clip = None
    try:
        clip = VideoFileClip(str(video_path))
        if clip.audio is None:
            raise ValueError(f"Video '{video_path.name}' has no audio track.")

        clip.audio.write_audiofile(
            str(output_path),
            fps=16_000,
            nbytes=2,
            ffmpeg_params=["-ac", "1"],
            logger=None,
        )
        logger.info(f"Audio extracted: {output_path.stat().st_size / 1_000:.0f} KB")
        return str(output_path)

    except (ValueError, FileNotFoundError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Audio extraction failed: {exc}") from exc
    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Metadata Extraction
# ---------------------------------------------------------------------------

def get_video_metadata(file_path: str) -> VideoMetadata:
    """
    Extract duration, resolution, and FPS from a video file using MoviePy.

    Safe: always returns a VideoMetadata (metadata_available=False on error).
    Must be called via asyncio.to_thread() from async FastAPI endpoints.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"get_video_metadata: file not found → {file_path}")
        return _unavailable_metadata()

    clip = None
    try:
        from moviepy import VideoFileClip

        logger.info(f"Opening VideoFileClip: {file_path}")
        clip = VideoFileClip(str(path), audio=False)
        duration_secs = float(clip.duration or 0.0)
        width, height = clip.size
        fps = float(clip.fps or 0.0)

        return VideoMetadata(
            duration_seconds=round(duration_secs, 2),
            duration_formatted=_format_duration(duration_secs),
            width=int(width),
            height=int(height),
            fps=round(fps, 2),
            metadata_available=True,
        )

    except Exception as exc:
        logger.warning(f"get_video_metadata failed for '{file_path}': {exc}")
        return _unavailable_metadata()

    finally:
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass


def _unavailable_metadata() -> VideoMetadata:
    return VideoMetadata(
        duration_seconds=0.0,
        duration_formatted="Unknown",
        width=0,
        height=0,
        fps=0.0,
        metadata_available=False,
    )


# ---------------------------------------------------------------------------
# Main Rendering Function
# ---------------------------------------------------------------------------

def render_clip(
    source_path: str,
    job_dir: str,
    start: float,
    end: float,
    headline: str,
    nugget_index: int,
    transcript_segments: Optional[list[dict]] = None,
    face_track: bool = True,
) -> RenderedClip:
    """
    Full 9:16 rendering pipeline for a single Golden Nugget.

    Pipeline:
      1. Load source VideoFileClip
      2. Subclip to [start, end]
      3. Sample 5 frames → MediaPipe face detection → median X centre
      4. compute_crop_box() → 9:16 crop window
      5. clip.cropped() → vertical strip
      6. PIL headline overlay (glassmorphic, top)
      7. PIL karaoke captions (bottom, time-synced per transcript segment)
      8. CompositeVideoClip → write_videofile(preset="ultrafast")
      9. Strict resource cleanup (clip.close() in finally)

    This is a SYNCHRONOUS blocking call — invoke via asyncio.to_thread() from
    async FastAPI endpoints.

    Args:
        source_path:         Path to the uploaded source video.
        job_dir:             Output directory (output/{video_id}/).
        start:               Clip start in seconds.
        end:                 Clip end in seconds (capped at start+60).
        headline:            GoldenNugget.headline for the top overlay.
        nugget_index:        Used for output filename (clip_00.mp4, clip_01.mp4, …).
        transcript_segments: List of {start, end, text} dicts for karaoke captions.
        face_track:          Whether to attempt MediaPipe face detection.

    Returns:
        RenderedClip with output_path, dimensions, and face_tracked flag.

    Raises:
        FileNotFoundError: source_path does not exist.
        RuntimeError:      Any MoviePy / ffmpeg encoding failure.
    """
    from moviepy import VideoFileClip, CompositeVideoClip, ImageClip

    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source video not found: {source_path}")

    job_dir_path = Path(job_dir)
    job_dir_path.mkdir(parents=True, exist_ok=True)
    output_path = job_dir_path / f"clip_{nugget_index:02d}.mp4"

    # Enforce 60s cap
    end = min(end, start + 60.0)

    logger.info(
        f"[render_clip] Starting: {source_path.name} "
        f"[{start:.1f}s → {end:.1f}s] → {output_path.name}"
    )

    main_clip = None
    try:
        # ── 1. Load & trim ───────────────────────────────────────────────────
        main_clip = VideoFileClip(str(source_path))
        subclip = main_clip.subclipped(start, end)
        src_w, src_h = subclip.size
        logger.info(f"[render_clip] Source: {src_w}×{src_h} @ {main_clip.fps:.0f}fps")

        # ── 2. Face position sampling ─────────────────────────────────────────
        face_cx, face_tracked = src_w // 2, False
        if face_track:
            try:
                face_cx, face_tracked = sample_face_position(subclip, n_samples=5)
            except Exception as fd_exc:
                logger.warning(f"[render_clip] Face sampling error: {fd_exc} — centre crop")

        logger.info(
            f"[render_clip] Face X={face_cx} "
            f"({'tracked' if face_tracked else 'centre crop'})"
        )

        # ── 3. 9:16 crop ──────────────────────────────────────────────────────
        x1, y1, x2, y2 = compute_crop_box(src_w, src_h, face_cx)
        cropped = subclip.cropped(x1=x1, y1=y1, x2=x2, y2=y2)
        crop_w, crop_h = cropped.size
        logger.info(f"[render_clip] Cropped: {crop_w}×{crop_h} (x1={x1}, x2={x2})")

        # ── 4. Headline overlay ────────────────────────────────────────────────
        hl_arr = _draw_headline_overlay(crop_w, crop_h, headline)
        headline_clip = (
            ImageClip(hl_arr)
            .with_duration(cropped.duration)
        )

        # ── 5. Karaoke caption clips ───────────────────────────────────────────
        caption_clips: list = []
        if transcript_segments:
            for seg in transcript_segments:
                seg_start = seg.get("start", 0.0) - start
                seg_end   = seg.get("end", 0.0)   - start
                text      = seg.get("text", "").strip()

                if not text or seg_end <= 0 or seg_start >= cropped.duration:
                    continue

                seg_start = max(0.0, seg_start)
                seg_end   = min(cropped.duration, seg_end)
                dur = seg_end - seg_start
                if dur < 0.1:
                    continue

                cap_arr = _draw_caption_overlay(crop_w, crop_h, text)
                cap_clip = (
                    ImageClip(cap_arr)
                    .with_start(seg_start)
                    .with_duration(dur)
                )
                caption_clips.append(cap_clip)

        logger.info(f"[render_clip] {len(caption_clips)} karaoke caption segments")

        # ── 6. Composite & encode ─────────────────────────────────────────────
        layers = [cropped, headline_clip] + caption_clips
        final = CompositeVideoClip(layers, size=(crop_w, crop_h))

        final.write_videofile(
            str(output_path),
            fps=main_clip.fps,
            preset="ultrafast",          # speed over compression ratio
            codec="libx264",
            audio_codec="aac",
            ffmpeg_params=["-pix_fmt", "yuv420p"], # Windows/mobile compatibility
            logger=None,                 # suppress ffmpeg progress
            threads=2,                   # conservative on CPU-only laptop
        )

        file_size_mb = output_path.stat().st_size / 1_000_000
        logger.info(
            f"[render_clip] ✓ {output_path.name} — "
            f"{crop_w}×{crop_h}, {end - start:.1f}s, {file_size_mb:.1f}MB"
        )

        return RenderedClip(
            job_id=job_dir_path.name,
            clip_index=nugget_index,
            output_path=str(output_path),
            duration=round(end - start, 2),
            width=crop_w,
            height=crop_h,
            face_tracked=face_tracked,
        )

    except FileNotFoundError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Render failed: {exc}") from exc
    finally:
        # Meticulous cleanup — critical on CPU-only laptops to free RAM + handles
        if main_clip is not None:
            try:
                main_clip.close()
                logger.debug("[render_clip] VideoFileClip closed ✓")
            except Exception as close_exc:
                logger.debug(f"[render_clip] clip.close() non-critical error: {close_exc}")


# ---------------------------------------------------------------------------
# Audio Analysis Service (stub — Librosa integration is future work)
# ---------------------------------------------------------------------------

class AudioSpikeService:
    """Detects high-energy moments in audio via Librosa (secondary virality signal)."""

    def __init__(self, energy_threshold: float = 0.75):
        self.energy_threshold = energy_threshold

    def detect_spikes(self, audio_path: str) -> list[AudioSpike]:
        logger.info(f"Detecting audio spikes (stub): {audio_path}")
        return [
            AudioSpike(timestamp=12.5, energy=0.91, duration=3.0),
            AudioSpike(timestamp=47.0, energy=0.88, duration=2.5),
        ]


# ---------------------------------------------------------------------------
# Convenience singleton factories
# ---------------------------------------------------------------------------

_audio_service: Optional[AudioSpikeService] = None


def get_audio_service() -> AudioSpikeService:
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioSpikeService()
    return _audio_service
