# AttentionX ⚡
### AI-Powered Video Repurposing Engine

> Transform long-form video into viral 60-second Shorts using **Narrative Intelligence** — not just audio spikes.

AttentionX uses **Gemini 2.5 Flash** to identify semantic story arcs (Hook → Agitation → Solution) in transcripts, **Whisper v3 Turbo** for blazing-fast transcription, and **MediaPipe** for face-tracked smart 9:16 cropping.

---

## 🏗️ Architecture

```
AttentionX/
├── app/                    # FastAPI backend
│   ├── main.py             # App entry point, CORS, routers
│   ├── routers/
│   │   ├── health.py       # GET  /health
│   │   ├── upload.py       # POST /api/v1/upload   ✅ Live
│   │   ├── analyze.py      # POST /api/v1/analyze  🔧 Prompt #3
│   │   └── export.py       # POST /api/v1/export   🔧 Prompt #4
│   └── services/
│       ├── ai_service.py   # Gemini + Whisper logic
│       └── video_service.py # MoviePy + MediaPipe + Librosa
├── frontend/
│   └── ui.py               # Streamlit dark-mode UI
├── output/                 # Generated clips (gitignored)
├── .env.template           # Copy to .env and fill in keys
└── requirements.txt
```

---

## 🚀 First-Time Setup & Run Guide

### Prerequisites
- Python 3.11+ (3.13 confirmed working)
- Git
- **Two terminal windows** — one for the API, one for the UI

### Step 1 — Clone & enter the repo
```powershell
git clone https://github.com/hmcommits/AttentionX.git
cd AttentionX
```

### Step 2 — Create and activate a virtual environment
```powershell
# Create venv
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\activate

# You should see (venv) in your prompt
```

> **Linux / macOS:** use `source venv/bin/activate` instead. On Windows, `source` is not valid — use `.\venv\Scripts\activate`.

### Step 3 — Install all dependencies
```powershell
pip install -r requirements.txt
```
> ⚠️ This installs heavy packages (MoviePy, MediaPipe, Whisper). Expect 3–5 minutes on first run.

### Step 4 — Set up your environment
```powershell
# Copy the template
copy .env.template .env

# Open .env and fill in your Gemini API key:
#   GEMINI_API_KEY=your_real_key_here
```
Get a free Gemini API key at: https://aistudio.google.com/app/apikey

### Step 5 — Start the FastAPI backend
**In Terminal 1** (keep this running):
```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Verify it's live: http://localhost:8000/health → should return `{"status":"ok"}`

Interactive API docs: http://localhost:8000/docs

### Step 6 — Start the Streamlit frontend
**In Terminal 2** (new window, same venv activated):
```powershell
streamlit run frontend/ui.py
```
The UI will open automatically at: http://localhost:8501

---

## 🔑 API Keys Required

| Key | Where to get it | Required for |
|---|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) | Narrative arc analysis (Prompt #3) |

> Steps 1–2 (upload + metadata) work **without any API key**.

---

## 🧪 Quick Test (no API key needed)

1. Start both servers (Steps 5 & 6 above)
2. Open http://localhost:8501
3. Upload any `.mp4` file
4. Click **⚡ Extract Viral Clips**
5. You should see the **Video Info** panel with duration, resolution, and FPS

---

## 🗺️ Roadmap

| Phase | Status | What it does |
|---|---|---|
| Scaffolding | ✅ Done | Project structure, FastAPI skeleton, Streamlit UI |
| Upload Pipeline | ✅ Done | Chunked upload, MIME verification, metadata extraction |
| AI Analysis | 🔧 Next | Whisper transcription + Gemini narrative arc detection |
| Export Pipeline | 🔧 Planned | MoviePy rendering + MediaPipe face-tracked 9:16 crop |

---

## ⚙️ Common Issues

| Problem | Fix |
|---|---|
| `source: not recognized` | Use `.\venv\Scripts\activate` on Windows PowerShell |
| `ModuleNotFoundError` | Make sure venv is active and you ran `pip install -r requirements.txt` |
| Sidebar shows `● OFFLINE` | Start the backend first: `uvicorn app.main:app --reload` |
| Upload fails with 400 | Only `.mp4` and `.mov` files accepted; file must be a real video |
| MoviePy ffmpeg error | Run `pip install imageio[ffmpeg]` to pull the ffmpeg binary |