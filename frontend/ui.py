"""
AttentionX — Streamlit Frontend
================================
A state-of-the-art dark-mode UI for the AttentionX video repurposing engine.
Run with:
    streamlit run frontend/ui.py
"""

import time
import requests
import streamlit as st
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

# ---------------------------------------------------------------------------
# Page Config (must be the FIRST Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AttentionX — AI Shorts Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — dark glassmorphism theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  /* ── Global ── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0a0a0f;
    color: #e2e8f0;
  }

  /* ── Main container ── */
  .block-container {
    padding-top: 2rem;
    max-width: 1100px;
  }

  /* ── Hero header ── */
  .hero-title {
    font-size: 3rem;
    font-weight: 700;
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.25rem;
  }
  .hero-sub {
    font-size: 1.1rem;
    color: #94a3b8;
    margin-bottom: 2rem;
  }

  /* ── Glass card ── */
  .glass-card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    backdrop-filter: blur(10px);
  }

  /* ── Status badge ── */
  .badge-ok   { color: #22c55e; font-weight: 600; }
  .badge-down { color: #ef4444; font-weight: 600; }
  .badge-warn { color: #f59e0b; font-weight: 600; }

  /* ── Streamlit overrides ── */
  .stButton > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.6rem 2rem;
    font-weight: 600;
    font-size: 1rem;
    transition: opacity 0.2s ease;
    width: 100%;
  }
  .stButton > button:hover { opacity: 0.85; }

  div[data-testid="stFileUploader"] {
    border: 2px dashed rgba(99, 102, 241, 0.4);
    border-radius: 12px;
    padding: 1rem;
    background: rgba(99, 102, 241, 0.04);
  }

  .stProgress > div > div {
    background: linear-gradient(90deg, #6366f1, #ec4899);
  }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8000"
ACCEPTED_TYPES = ["mp4", "mov"]

# ---------------------------------------------------------------------------
# Session State Initialisation
# ---------------------------------------------------------------------------
if "video_id" not in st.session_state:
    st.session_state.video_id = None          # UUID returned by /upload
if "video_metadata" not in st.session_state:
    st.session_state.video_metadata = None    # dict from API VideoMetadataResponse
if "source_file_path" not in st.session_state:
    st.session_state.source_file_path = None  # used by /analyze in Prompt #3
if "clips" not in st.session_state:
    st.session_state.clips = []
if "processing_done" not in st.session_state:
    st.session_state.processing_done = False
if "upload_error" not in st.session_state:
    st.session_state.upload_error = None

# ---------------------------------------------------------------------------
# Sidebar — API Status & Settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚡ AttentionX")
    st.markdown("---")

    # Live API health check
    st.markdown("### 🔌 Backend Status")
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            st.markdown(
                f'<span class="badge-ok">● ONLINE</span> — {data.get("service", "API")} v{data.get("version", "?")}',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span class="badge-warn">● DEGRADED</span>', unsafe_allow_html=True)
    except requests.exceptions.ConnectionError:
        st.markdown(
            '<span class="badge-down">● OFFLINE</span><br>'
            '<small>Start the API: <code>uvicorn app.main:app --reload</code></small>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    max_clips = st.slider("Max clips to extract", min_value=1, max_value=10, value=5)
    clip_duration = st.slider("Max clip length (sec)", min_value=30, max_value=90, value=60)
    face_track = st.toggle("Smart face-tracking crop", value=True)

    st.markdown("---")
    st.markdown("### 📖 About")
    st.markdown(
        "AttentionX uses **Narrative Intelligence** to find "
        "Hook → Agitation → Solution arcs — not just loud moments.",
        help="Powered by Gemini 2.5 Flash + Whisper v3 Turbo",
    )

# ---------------------------------------------------------------------------
# Main — Hero Header
# ---------------------------------------------------------------------------
st.markdown('<h1 class="hero-title">AttentionX ⚡</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-sub">Transform long-form video into viral 60-second Shorts '
    'using AI Narrative Intelligence.</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Main — Upload Section
# ---------------------------------------------------------------------------
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.markdown("### 📁 Upload Your Video")
st.markdown("Supports `.mp4` and `.mov` — up to 2 GB. Longer videos yield better results.")

uploaded_file = st.file_uploader(
    label="Drop your video here or click to browse",
    type=ACCEPTED_TYPES,
    label_visibility="collapsed",
)

if uploaded_file:
    col1, col2, col3 = st.columns(3)
    col1.metric("📄 File", uploaded_file.name)
    col2.metric("📦 Size", f"{uploaded_file.size / 1_000_000:.1f} MB")
    col3.metric("🎞️ Type", uploaded_file.type or "video")

# ── Video Info Panel (shown after successful upload) ──────────────────────────
if st.session_state.video_metadata:
    meta = st.session_state.video_metadata
    st.markdown("---")
    st.markdown("#### 📊 Video Info")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "🕐 Duration",
        meta.get("duration_formatted", "—"),
        help=f"{meta.get('duration_seconds', 0):.1f} seconds total",
    )
    m2.metric(
        "📐 Resolution",
        f"{meta.get('width', 0)}×{meta.get('height', 0)}",
        help="Source video resolution",
    )
    m3.metric(
        "🎞️ FPS",
        f"{meta.get('fps', 0):.2f}",
        help="Frames per second",
    )
    m4.metric(
        "🆔 Video ID",
        st.session_state.video_id[:8] + "…" if st.session_state.video_id else "—",
        help=f"Full ID: {st.session_state.video_id}",
    )
    if not meta.get("metadata_available", True):
        st.warning(
            "⚠️  Metadata extraction failed (file may use an unsupported codec). "
            "Processing will continue — clip timestamps may be approximate.",
            icon="⚠️",
        )

if st.session_state.upload_error:
    st.error(f"❌ Upload failed: {st.session_state.upload_error}")

st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Main — Process Button + Pipeline
# ---------------------------------------------------------------------------
process_btn = st.button(
    "⚡ Extract Viral Clips",
    disabled=uploaded_file is None,
)

if process_btn and uploaded_file:
    st.session_state.processing_done = False
    st.session_state.clips = []
    st.session_state.upload_error = None
    st.session_state.video_metadata = None

    # ── st.status containers (Streamlit 1.28+) ──────────────────────────────
    with st.status("🚀 Running AttentionX Pipeline...", expanded=True) as status:

        # ── STEP 1: Real chunked upload ──────────────────────────────────────
        st.write("📤 **Step 1 of 4** — Sending video to API (chunked stream)...")
        upload_ok = False
        try:
            # Reset the file pointer before sending
            uploaded_file.seek(0)

            st.write("  ↳ Verifying file format (magic bytes)...")
            resp = requests.post(
                f"{API_BASE}/api/v1/upload",
                files={"file": (uploaded_file.name, uploaded_file, uploaded_file.type or "video/mp4")},
                timeout=(10, None),  # 10s to connect, unlimited for large file transfers
            )

            if resp.status_code == 201:
                data = resp.json()
                st.session_state.video_id = data["video_id"]
                st.session_state.source_file_path = data["file_path"]
                st.session_state.video_metadata = data["metadata"]
                meta = data["metadata"]

                st.write("  ↳ Extracting video metadata (MoviePy)...")
                time.sleep(0.3)  # brief pause so the user sees the step

                st.write(
                    f"✅ Upload complete — "
                    f"`{data['original_filename']}` · "
                    f"`{data['file_size_mb']} MB` · "
                    f"`{meta.get('duration_formatted', '?')}` · "
                    f"`{meta.get('width', '?')}×{meta.get('height', '?')}` · "
                    f"`{meta.get('fps', '?')} fps`"
                )
                upload_ok = True

            else:
                error_detail = resp.json().get("detail", resp.text)
                st.session_state.upload_error = error_detail
                status.update(
                    label=f"❌ Upload rejected: {error_detail}",
                    state="error",
                    expanded=True,
                )

        except RequestsConnectionError:
            msg = "Cannot connect to API. Is `uvicorn app.main:app --reload` running?"
            st.session_state.upload_error = msg
            status.update(label=f"❌ {msg}", state="error", expanded=True)

        except Exception as exc:
            msg = str(exc)
            st.session_state.upload_error = msg
            status.update(label=f"❌ Unexpected error: {msg}", state="error", expanded=True)

        if not upload_ok:
            st.stop()

        # ── STEP 2: Whisper transcription (stub — Prompt #3) ─────────────────
        st.write("🎙️ **Step 2 of 4** — Transcribing audio (Whisper v3 Turbo)...")
        time.sleep(1.2)   # TODO (Prompt #3): replace with real Whisper call
        st.write("✅ Transcript ready")

        # ── STEP 3: Gemini analysis (stub — Prompt #3) ───────────────────────
        st.write("🧠 **Step 3 of 4** — Analysing narrative arcs (Gemini 2.5 Flash)...")
        time.sleep(1.5)   # TODO (Prompt #3): replace with real Gemini call
        st.write("✅ 5 story arcs identified")

        # ── STEP 4: Rendering (stub — Prompt #4) ─────────────────────────────
        st.write("🎬 **Step 4 of 4** — Rendering clips with face-tracked 9:16 crop...")
        time.sleep(1.0)   # TODO (Prompt #4): replace with real MoviePy/MediaPipe render
        st.write("✅ Clips rendered")

        status.update(label="✅ Pipeline complete!", state="complete", expanded=False)

    st.session_state.processing_done = True

    # Placeholder clips for UI preview
    st.session_state.clips = [
        {
            "index": i + 1,
            "hook": f"Hook #{i+1} — [populated by Gemini in Prompt #3]",
            "virality_score": round(0.95 - i * 0.07, 2),
            "duration": "0:58",
            "path": None,
        }
        for i in range(max_clips)
    ]

# ---------------------------------------------------------------------------
# Main — Results Grid
# ---------------------------------------------------------------------------
if st.session_state.processing_done and st.session_state.clips:
    st.markdown("---")
    st.markdown("### 🎯 Extracted Clips")
    st.markdown(
        f"Found **{len(st.session_state.clips)} clips** ranked by Narrative Virality Score."
    )

    for clip in st.session_state.clips:
        with st.expander(
            f"📹 Clip #{clip['index']}  —  Score: {clip['virality_score']:.0%}  |  {clip['duration']}",
            expanded=clip["index"] == 1,
        ):
            col_preview, col_meta = st.columns([2, 1])

            with col_preview:
                if clip["path"]:
                    st.video(clip["path"])
                else:
                    st.info(
                        "🎬 Video preview available after Prompt #4 "
                        "(MoviePy rendering pipeline).",
                        icon="ℹ️",
                    )

            with col_meta:
                st.markdown(f"**Hook:** {clip['hook']}")
                st.markdown(f"**Duration:** {clip['duration']}")
                st.progress(clip["virality_score"])
                st.markdown(f"**Virality Score:** `{clip['virality_score']:.0%}`")

                st.button(
                    "⬇️ Download Clip",
                    key=f"dl_{clip['index']}",
                    disabled=clip["path"] is None,
                )
