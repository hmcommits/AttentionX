"""
AttentionX — Upload Router
POST /api/v1/upload  →  accepts video file, saves to output dir, returns job_id

Implemented fully in Prompt #2.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/upload", summary="Upload a video file for processing")
async def upload_video():
    """
    Accepts an .mp4 / .mov file upload.
    Saves it to the output directory and returns a unique job_id.

    TODO (Prompt #2): Implement multipart file upload with background job queue.
    """
    return {"message": "Upload endpoint — coming in Prompt #2", "job_id": None}
