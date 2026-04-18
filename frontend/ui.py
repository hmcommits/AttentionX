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
from pathlib import Path
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
# Load Custom CSS
# ---------------------------------------------------------------------------
def _load_css():
    css_path = Path(__file__).parent / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

_load_css()

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
        "Hook → Story Arc → Payoff moments.",
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
# Main — Hero Header & 1-2-3 Onboarding Flow
# ---------------------------------------------------------------------------
st.markdown('<div class="animated-fade">', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">AttentionX ⚡</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-sub">Transform long-form video into viral 60-second Shorts '
    'using AI Narrative Intelligence.</p>',
    unsafe_allow_html=True,
)

# 1-2-3 Flow
st.markdown("""
<div class="onboarding-flow">
    <div class="onboarding-step">
        <span class="onboarding-icon">📁</span>
        <div class="onboarding-title">1. Drop a video</div>
        <div class="onboarding-desc">Upload a podcast, interview, or any long-form content.</div>
    </div>
    <div class="onboarding-step">
        <span class="onboarding-icon">🧠</span>
        <div class="onboarding-title">2. AI Analysis</div>
        <div class="onboarding-desc">Gemini identifies viral storytelling arcs (hooks, tension, payoff).</div>
    </div>
    <div class="onboarding-step">
        <span class="onboarding-icon">📱</span>
        <div class="onboarding-title">3. Export Shorts</div>
        <div class="onboarding-desc">Render face-tracked 9:16 vertical clips with karaoke captions.</div>
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)


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
        type="primary"
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

            # ── Rationale & Transcript (Side-by-Side UI) ─────────────────────
            # Clean CSS-based content formatting to avoid markdown artifacting
            rat_col, trans_col = st.columns(2, gap="large")
            with rat_col:
                st.markdown("💡 **Why it's viral**")
                if rationale:
                    st.markdown(
                        f'<div class="nugget-rationale">{rationale}</div>',
                        unsafe_allow_html=True,
                    )
            with trans_col:
                st.markdown("📄 **Transcript snippet**")
                if snippet:
                    st.markdown(
                        f'<div class="nugget-transcript">{snippet}</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Render / Video display ───────────────────────────────────────
            clip_url_key   = f"clip_url_{i}"
            clip_error_key = f"clip_error_{i}"

            if st.session_state.get(clip_error_key):
                st.error(f"❌ Render failed: {st.session_state[clip_error_key]}")
                if st.button("🔄 Try Again", key=f"retry_{i}"):
                    st.session_state[clip_error_key] = None
                    st.rerun()

            elif st.session_state.get(clip_url_key):
                # ── Clip already rendered — show player & download ───────────
                clip_url = st.session_state[clip_url_key]
                st.success("🎬 Vertical clip ready!")
                
                # Center the video and limit height so it doesn't take over screen
                vid_col, _, = st.columns([1, 2])
                with vid_col:
                    st.video(clip_url)

                try:
                    clip_bytes = requests.get(clip_url, timeout=30).content
                    st.download_button(
                        label="⬇️ Download Vertical Clip",
                        data=clip_bytes,
                        file_name=f"attentionx_nugget_{i + 1}.mp4",
                        mime="video/mp4",
                        key=f"dl_btn_{i}",
                        use_container_width=True,
                        type="primary"
                    )
                except Exception:
                    st.info("📥 Clip is ready — use the URL above to download.")

            else:
                # ── Render button (not yet rendered) ─────────────────────────
                if st.session_state.video_id is None:
                    st.info("Upload a video first to enable rendering.")
                else:
                    render_btn = st.button(
                        "🎬 Generate Vertical Video",
                        key=f"render_{i}",
                        use_container_width=True,
                        type="primary"
                    )

                    if render_btn:
                        st.session_state[clip_error_key] = None
                        with st.status(
                            "🎬 Rendering 9:16 vertical clip...",
                            expanded=True,
                        ) as render_status:
                            st.write("🔍  Sampling frames for face position (MediaPipe)...")
                            st.write("✂️  Applying 9:16 crop & caption overlays (PIL)...")
                            st.write("⚙️  Encoding with ultrafast preset...")

                            try:
                                resp = requests.post(
                                    f"{API_BASE}/api/v1/export/"
                                    f"{st.session_state.video_id}/{i}",
                                    timeout=(10, None),
                                )

                                if resp.status_code == 200:
                                    data = resp.json()
                                    # UI Persistence: save to session_state immediately
                                    st.session_state[clip_url_key] = data["clip_url"]

                                    face_info = (
                                        "✅ Face-tracked"
                                        if data.get("face_tracked")
                                        else "📐 Centre crop"
                                    )
                                    cached_note = " (cached)" if data.get("cached") else ""
                                    render_status.update(
                                        label=(
                                            f"✅ Clip ready!{cached_note} "
                                            f"{face_info} · "
                                            f"{data.get('width','?')}×{data.get('height','?')}"
                                        ),
                                        state="complete",
                                        expanded=False,
                                    )
                                else:
                                    err = resp.json().get("detail", "Render failed")
                                    st.session_state[clip_error_key] = err
                                    render_status.update(
                                        label=f"❌ {err}", state="error", expanded=True
                                    )

                            except RequestsConnectionError:
                                err = "Cannot connect to API server."
                                st.session_state[clip_error_key] = err
                                render_status.update(
                                    label=f"❌ {err}", state="error", expanded=True
                                )
                            except Exception as exc:
                                err = str(exc)
                                st.session_state[clip_error_key] = err
                                render_status.update(
                                    label=f"❌ {err}", state="error", expanded=True
                                )

                        st.rerun()

    # ── Re-Analyze option ─────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("🔄 Re-Analyze (clear cache & re-run)", key="reanalyze_btn"):
        # Clear analysis state — rendered clips are preserved in output/ dir
        st.session_state.analysis_done = False
        st.session_state.golden_nuggets = []
        st.session_state.analysis_cached = False
        st.session_state.analysis_error = None
        # Clear any per-clip render state
        for k in list(st.session_state.keys()):
            if k.startswith("clip_url_") or k.startswith("clip_error_"):
                del st.session_state[k]
        st.rerun()
