"""
AttentionX — Export Router
POST /api/v1/export  →  triggers MoviePy clip rendering + MediaPipe face-crop

Implemented fully in Prompt #4.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/export", summary="Render and export selected clips")
async def export_clips():
    """
    Accepts a list of clip segments and renders them:
      1. MoviePy — trim, encode to 9:16 aspect ratio
      2. MediaPipe — face-track speaker, keep them centred throughout
      3. Returns download URLs for rendered clips

    TODO (Prompt #4): Implement full rendering pipeline with MediaPipe crop.
    """
    return {"message": "Export endpoint — coming in Prompt #4", "download_urls": []}
