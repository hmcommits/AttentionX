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
if "job_id" not in st.session_state:
    st.session_state.job_id = None
if "clips" not in st.session_state:
    st.session_state.clips = []
if "processing_done" not in st.session_state:
    st.session_state.processing_done = False

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

    # ── st.status containers (Streamlit 1.28+) ──────────────────────────────
    with st.status("🚀 Running AttentionX Pipeline...", expanded=True) as status:

        st.write("📤 **Step 1 of 4** — Uploading video to API...")
        time.sleep(0.8)   # TODO: replace with real API call (Prompt #2)
        st.write("✅ Upload complete")

        st.write("🎙️ **Step 2 of 4** — Transcribing audio (Whisper v3 Turbo)...")
        time.sleep(1.2)   # TODO: replace with real Whisper call (Prompt #3)
        st.write("✅ Transcript ready")

        st.write("🧠 **Step 3 of 4** — Analysing narrative arcs (Gemini 2.5 Flash)...")
        time.sleep(1.5)   # TODO: replace with real Gemini call (Prompt #3)
        st.write("✅ 5 story arcs identified")

        st.write("🎬 **Step 4 of 4** — Rendering clips with face-tracked 9:16 crop...")
        time.sleep(1.0)   # TODO: replace with real MoviePy/MediaPipe render (Prompt #4)
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
