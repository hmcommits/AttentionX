<div align="center">
  
# ⚡ AttentionX

**The fully autonomous, AI-driven video repurposing engine.**
Transform hours of long-form video (podcasts, interviews, keynotes) into highly-viral, 60-second vertical Shorts using state-of-the-art Narrative Intelligence.

[![Python](https://img.shields.io/badge/Python-3.11+-3b82f6.svg?style=flat&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B.svg?style=flat&logo=streamlit)](https://streamlit.io)
[![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-AI-8b5cf6.svg?style=flat&logo=google)](https://ai.google.dev/)

<br>

**[🌍 View Live Application](https://attentionx-ui-production.up.railway.app/)** | **[🎬 Watch Demo Video](https://drive.google.com/file/d/1VxejpV63GaUFptoqXc3Qo6bhsDrd2unX/view?usp=sharing)**

</div>

---

## 🚀 The Vision

Most AI clipping tools search your video for "loud noises" or arbitrary timestamps and call it a day, resulting in robotic, contextless clips. 

**AttentionX** operates on a completely different paradigm. Using **Narrative Intelligence**, it transcribes your entire video with `faster-whisper` and pipes the data into a high-context reasoning model (Gemini 2.5 Flash). Gemini analyzes the transcript specifically for the structural mechanics of a viral video: a strong **Hook**, an engaging **Story Arc**, and a satisfying **Payoff**. 

It ranks the top "Golden Nuggets" by Virality Score, tracks the speaker's face, renders karaoke captions, and exports a 9:16 vertical video right to your browser.

## 🛠️ Architecture & Stack

AttentionX is a modular, decentralized application separated into a heavy-compute REST API backend and a lightweight, premium glassmorphic frontend.

* **Backend API**: `FastAPI`, `Uvicorn`, `MoviePy` (Video Processing)
* **AI Core**: `faster-whisper` (16kHz Audio Transcription), `google-genai` (LLM Analysis)
* **Computer Vision**: `MediaPipe` (Spatial Face-Tracking via median sampling)
* **Frontend UI**: `Streamlit` with custom CSS (Outfit/Inter typography, animated `@keyframes`)
* **Deployment**: `Nixpacks`, `Railway.app` ready.

---

## ✨ Key Features

- **🧠 Semantic Narrative AI**: Exclusively hunts for storytelling structures rather than random audio spikes. Ranks outputs on a 1-10 Viral Score scale.
- **🎥 The Vision Engine**: Extracts a 9:16 vertical crop from a 16:9 source video by utilizing MediaPipe to spatially track the subject's face dynamically. 
- **📝 Zero-Dependency Captions**: Renders glassmorphic headlines and time-synchronized karaoke captions at the bottom of the screen completely natively using PIL (Pillow)—no `ImageMagick` binaries required.
- **⚡ Ultrafast Local Encoding**: Asynchronous background rendering pipelines optimized to leverage `libx264` and `yuv420p` compatible encoding, guaranteeing smooth playback on Windows Media Player and iOS natively.

---

## 💻 Running Locally

### 1. Prerequisites
Ensure you have the following installed on your system:
- Python 3.11 or higher
- `ffmpeg` (must be accessible in your system PATH)

### 2. Environment Setup
Clone the repository and install the dependencies:
```bash
git clone https://github.com/hmcommits/AttentionX.git
cd AttentionX

# Create and activate a virtual environment
python -m venv venv
# On Windows:
source venv/Scripts/activate
# On Mac/Linux:
# source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. API Key Configuration
Create a `.env` file in the root directory and add your Google Gemini AI key:
```env
GEMINI_API_KEY="your_google_ai_studio_api_key_here"
```

### 4. Booting the Application
AttentionX requires both the Backend (FastAPI) and Frontend (Streamlit) services to be running simultaneously in two separate terminals.

**Terminal 1 (Backend API):**
```bash
uvicorn app.main:app --reload
```

**Terminal 2 (Frontend UI):**
```bash
streamlit run frontend/ui.py
```
The glassmorphic dashboard will automatically open at `http://localhost:8501`.

---

## ☁️ Production Deployment (Railway)

**The live web app is currently deployed and hosted using [Railway.app](https://railway.app).**

AttentionX is architected for a zero-configuration deployment to Platform-as-a-Service providers like Railway or Render. 

The repository includes an `Aptfile` for Nixpacks to automatically pre-install the required `ffmpeg` binaries in the cloud environment natively, bypassing complex Docker containerization.

1. Create a New Project on Railway from this GitHub repository.
2. Deploy the **Backend API** using the provided `railway.json` configuration. Inject your `GEMINI_API_KEY` into the dashboard.
3. Deploy the **Frontend UI** as a second service. Start command: `streamlit run frontend/ui.py --server.port $PORT --server.address 0.0.0.0`. Inject the `API_URL` variable pointing to your backend service domain.

---

<div align="center">
  <i>Built for the 2026 content era.</i>
</div>