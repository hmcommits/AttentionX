"""
AttentionX — Streamlit Frontend (Phase 3: Two-Stage Flow + Golden Nuggets)
===========================================================================
Stage 1: Upload & Extract Info  → POST /api/v1/upload
Stage 2: Analyze for Virality   → POST /api/v1/analyze/{video_id}

Run with:
    streamlit run frontend/ui.py
"""

import time
import requests
import streamlit as st
from requests.exceptions import ConnectionError as RequestsConnectionError

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
# Custom CSS — dark glassmorphism + viral score badges
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

  /* ── Viral Score Badges ── */
  .vs-badge {
    display: inline-block;
    padding: 0.25em 0.75em;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.9rem;
    letter-spacing: 0.02em;
  }
  .vs-fire {
    background: rgba(239, 68, 68, 0.18);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.4);
  }
  .vs-hot {
    background: rgba(245, 158, 11, 0.18);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.4);
  }
  .vs-warm {
    background: rgba(99, 102, 241, 0.18);
    color: #818cf8;
    border: 1px solid rgba(99, 102, 241, 0.4);
  }

  /* ── Golden Nugget card header ── */
  .nugget-headline {
    font-size: 1.25rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0.3rem 0 0.5rem 0;
    line-height: 1.3;
  }
  .nugget-meta {
    font-size: 0.82rem;
    color: #64748b;
    margin-bottom: 0.6rem;
  }
  .nugget-rationale {
    color: #94a3b8;
    font-size: 0.95rem;
    line-height: 1.6;
    border-left: 3px solid rgba(99, 102, 241, 0.5);
    padding-left: 0.75rem;
    margin-top: 0.5rem;
  }

  /* ── Cached analysis badge ── */
  .cache-badge {
    display: inline-block;
    padding: 0.15em 0.6em;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    background: rgba(34, 197, 94, 0.12);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
    margin-left: 0.5rem;
  }

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
  .stButton > button:disabled {
    background: rgba(99, 102, 241, 0.25);
    opacity: 0.5;
  }

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
_defaults = {
    "video_id": None,
    "video_metadata": None,
    "source_file_path": None,
    "upload_error": None,
    # Phase 3
    "golden_nuggets": [],
    "transcript_segment_count": 0,
    "analysis_done": False,
    "analysis_cached": False,
    "analysis_error": None,
}
for key, val in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _viral_badge_html(score: int) -> str:
    """Return coloured viral score badge HTML."""
    if score >= 8:
        css_class, label = "vs-fire", f"🔥 {score}/10"
    elif score >= 5:
        css_class, label = "vs-hot", f"⚡ {score}/10"
    else:
        css_class, label = "vs-warm", f"📌 {score}/10"
    return f'<span class="vs-badge {css_class}">{label}</span>'


def _fmt_seconds(s: float) -> str:
    """Format seconds as M:SS."""
    m, sec = divmod(int(s), 60)
    return f"{m}:{sec:02d}"


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
                f'<span class="badge-ok">● ONLINE</span> — {data.get("service","API")} v{data.get("version","?")}',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span class="badge-warn">● DEGRADED</span>', unsafe_allow_html=True)
    except requests.exceptions.ConnectionError:
        st.markdown(
            '<span class="badge-down">● OFFLINE</span><br>'
            '<small>Start: <code>uvicorn app.main:app --reload</code></small>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    max_clips = st.slider("Golden Nuggets to find", min_value=1, max_value=10, value=3)
    face_track = st.toggle("Smart face-tracking crop", value=True)

    st.markdown("---")
    st.markdown("### 📖 About")
    st.markdown(
        "AttentionX uses **Narrative Intelligence** to find "
        "Hook → Story Arc → Payoff moments — not just loud audio spikes.",
        help="Powered by Gemini 2.5 Flash + Whisper + MediaPipe",
    )

    # Show current job info if available
    if st.session_state.video_id:
        st.markdown("---")
        st.markdown("### 🎬 Active Job")
        st.code(st.session_state.video_id[:18] + "…", language=None)
        if st.button("🗑️ Clear & Start Over", use_container_width=True):
            for key in _defaults:
                st.session_state[key] = _defaults[key]
            st.rerun()


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
# ── STAGE 1: Upload ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.markdown("### 📁 Step 1 — Upload Your Video")
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

# ── Video Info Panel (shown after successful upload) ─────────────────────────
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
        f"{meta.get('fps', 0):.0f}",
        help="Frames per second",
    )
    m4.metric(
        "🆔 Video ID",
        (st.session_state.video_id[:8] + "…") if st.session_state.video_id else "—",
        help=f"Full ID: {st.session_state.video_id}",
    )
    if not meta.get("metadata_available", True):
        st.warning(
            "⚠️  Metadata extraction failed. Processing will continue with default values.",
            icon="⚠️",
        )

if st.session_state.upload_error:
    st.error(f"❌ Upload failed: {st.session_state.upload_error}")

st.markdown("</div>", unsafe_allow_html=True)

# ── Upload Button ─────────────────────────────────────────────────────────────
upload_btn = st.button(
    "⚡ Upload & Extract Info",
    disabled=uploaded_file is None,
    key="upload_btn",
)

if upload_btn and uploaded_file:
    # Reset state for a fresh upload
    for key in _defaults:
        st.session_state[key] = _defaults[key]

    with st.status("📤 Uploading video to AttentionX...", expanded=True) as upload_status:
        st.write("🔍  Verifying file format (magic bytes)...")
        try:
            uploaded_file.seek(0)
            resp = requests.post(
                f"{API_BASE}/api/v1/upload",
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file,
                        uploaded_file.type or "video/mp4",
                    )
                },
                timeout=(10, None),   # 10s connect; unlimited for large files
            )

            if resp.status_code == 201:
                data = resp.json()
                st.session_state.video_id = data["video_id"]
                st.session_state.source_file_path = data["file_path"]
                st.session_state.video_metadata = data["metadata"]
                meta = data["metadata"]

                st.write("📐  Extracting video metadata (MoviePy)...")
                time.sleep(0.3)

                st.write(
                    f"✅ Upload complete — "
                    f"`{data['original_filename']}` · "
                    f"`{data['file_size_mb']} MB` · "
                    f"`{meta.get('duration_formatted','?')}` · "
                    f"`{meta.get('width','?')}×{meta.get('height','?')}` · "
                    f"`{meta.get('fps','?')} fps`"
                )
                upload_status.update(
                    label="✅ Upload complete! Click **Analyze for Virality** to find your Golden Nuggets.",
                    state="complete",
                    expanded=False,
                )
            else:
                err = resp.json().get("detail", resp.text)
                st.session_state.upload_error = err
                upload_status.update(
                    label=f"❌ Upload rejected: {err}",
                    state="error",
                    expanded=True,
                )

        except RequestsConnectionError:
            msg = "Cannot connect to API server. Is `uvicorn app.main:app --reload` running?"
            st.session_state.upload_error = msg
            upload_status.update(label=f"❌ {msg}", state="error", expanded=True)
        except Exception as exc:
            msg = str(exc)
            st.session_state.upload_error = msg
            upload_status.update(label=f"❌ Unexpected error: {msg}", state="error", expanded=True)

    st.rerun()


# ---------------------------------------------------------------------------
# ── STAGE 2: Analyze ─────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
if st.session_state.video_id and not st.session_state.analysis_done:
    st.markdown("---")
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🔍 Step 2 — Analyze for Virality")
    st.markdown(
        f"Video uploaded successfully. Click below to run the AI pipeline — "
        f"Whisper will transcribe the audio, then Gemini 2.5 Flash will identify "
        f"**{max_clips} Golden Nuggets** using Narrative Intelligence."
    )

    if st.session_state.analysis_error:
        st.error(f"❌ Analysis failed: {st.session_state.analysis_error}")

    st.markdown("</div>", unsafe_allow_html=True)

    analyze_btn = st.button(
        "🔍 Analyze for Virality",
        key="analyze_btn",
    )

    if analyze_btn:
        st.session_state.analysis_error = None

        with st.status(
            "🔍 AI is watching your video for golden nuggets...",
            expanded=True,
        ) as analyze_status:

            st.write("🎙️  Loading Whisper model (cached after first load)...")
            time.sleep(0.4)

            st.write("📝  Extracting 16kHz mono audio & transcribing speech...")

            try:
                resp = requests.post(
                    f"{API_BASE}/api/v1/analyze/{st.session_state.video_id}",
                    params={"max_clips": max_clips},
                    timeout=(10, None),   # transcription can take minutes
                )

                if resp.status_code == 200:
                    data = resp.json()
                    nuggets = data.get("golden_nuggets", [])
                    segment_count = data.get("transcript_segment_count", 0)
                    is_cached = data.get("cached", False)

                    st.write(
                        f"🧠  Gemini 2.5 Flash identified narrative arcs "
                        f"({segment_count} transcript segments analysed)..."
                    )
                    time.sleep(0.4)
                    st.write(f"🏆  Ranking the top **{len(nuggets)}** viral moments by hook strength...")
                    time.sleep(0.3)

                    st.session_state.golden_nuggets = nuggets
                    st.session_state.transcript_segment_count = segment_count
                    st.session_state.analysis_done = True
                    st.session_state.analysis_cached = is_cached

                    cache_note = " (loaded from cache)" if is_cached else ""
                    analyze_status.update(
                        label=f"✅ {len(nuggets)} Golden Nuggets found!{cache_note}",
                        state="complete",
                        expanded=False,
                    )

                elif resp.status_code == 400:
                    err = resp.json().get("detail", "Bad request")
                    st.session_state.analysis_error = err
                    analyze_status.update(label=f"❌ {err}", state="error", expanded=True)

                elif resp.status_code == 502:
                    err = resp.json().get("detail", "Gemini API error")
                    st.session_state.analysis_error = err
                    analyze_status.update(label=f"❌ Gemini error: {err}", state="error", expanded=True)

                else:
                    err = resp.json().get("detail", resp.text)
                    st.session_state.analysis_error = err
                    analyze_status.update(label=f"❌ Error {resp.status_code}: {err}", state="error", expanded=True)

            except RequestsConnectionError:
                msg = "Cannot connect to API server."
                st.session_state.analysis_error = msg
                analyze_status.update(label=f"❌ {msg}", state="error", expanded=True)
            except Exception as exc:
                msg = str(exc)
                st.session_state.analysis_error = msg
                analyze_status.update(label=f"❌ Unexpected error: {msg}", state="error", expanded=True)

        st.rerun()


# ---------------------------------------------------------------------------
# ── RESULTS: Golden Nuggets ───────────────────────────────────────────────────
# ---------------------------------------------------------------------------
if st.session_state.analysis_done and st.session_state.golden_nuggets:
    st.markdown("---")

    # Section header
    header_col, badge_col = st.columns([4, 1])
    with header_col:
        cache_html = (
            '<span class="cache-badge">⚡ Cached</span>'
            if st.session_state.analysis_cached else ""
        )
        st.markdown(
            f"### 🏆 Golden Nuggets{cache_html}",
            unsafe_allow_html=True,
        )
        n_segs = st.session_state.transcript_segment_count
        n_clips = len(st.session_state.golden_nuggets)
        st.markdown(
            f"Gemini analysed **{n_segs} transcript segments** and identified "
            f"**{n_clips} viral clips** ranked by hook strength.",
        )

    nuggets = sorted(
        st.session_state.golden_nuggets,
        key=lambda x: x.get("viral_score", 0),
        reverse=True,
    )

    for i, nugget in enumerate(nuggets):
        score = nugget.get("viral_score", 5)
        headline = nugget.get("headline", f"Clip #{i + 1}")
        rationale = nugget.get("rationale", "")
        start_s = nugget.get("start", 0.0)
        end_s = nugget.get("end", 0.0)
        duration = nugget.get("duration", end_s - start_s)
        snippet = nugget.get("transcript_snippet", "")

        badge_html = _viral_badge_html(score)
        label = f"#{i + 1}  {headline}"

        with st.expander(label, expanded=(i == 0)):
            # Top row: badge + timestamp bar
            info_col, score_col = st.columns([3, 1])
            with info_col:
                st.markdown(
                    f'<p class="nugget-meta">'
                    f"⏱ {_fmt_seconds(start_s)} → {_fmt_seconds(end_s)} &nbsp;·&nbsp; "
                    f"🕐 {duration:.1f}s"
                    f"</p>",
                    unsafe_allow_html=True,
                )
            with score_col:
                st.markdown(
                    f"**Viral Score**<br>{badge_html}",
                    unsafe_allow_html=True,
                )

            # Progress bar as virality meter
            st.progress(score / 10, text=f"Hook strength: {score}/10")

            # Rationale
            if rationale:
                st.markdown(
                    f'<p class="nugget-rationale">{rationale}</p>',
                    unsafe_allow_html=True,
                )

            # Transcript snippet
            if snippet:
                with st.expander("📄 Transcript excerpt", expanded=False):
                    st.markdown(f"> {snippet}")

            st.markdown("---")

            # Action row
            dl_col, export_col = st.columns(2)
            with dl_col:
                st.button(
                    "🎬 Render Clip",
                    key=f"render_{i}",
                    disabled=True,
                    help="Coming in Phase 4 — MoviePy rendering pipeline",
                )
            with export_col:
                st.button(
                    "⬇️ Download",
                    key=f"dl_{i}",
                    disabled=True,
                    help="Available after clip is rendered",
                )

    # Re-analyze option
    st.markdown("---")
    if st.button("🔄 Re-Analyze (clear cache)", key="reanalyze_btn"):
        # Clear analysis.json via file deletion triggers would need an API call;
        # for now, reset session state to allow re-running from the UI
        st.session_state.analysis_done = False
        st.session_state.golden_nuggets = []
        st.session_state.analysis_cached = False
        st.session_state.analysis_error = None
        st.rerun()
