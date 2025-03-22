from fastapi import APIRouter, UploadFile, HTTPException
from app.services import analyze_receipt

router = APIRouter()

@router.post("/analyze/")
async def analyze(file: UploadFile):
    try:
        return await analyze_receipt(file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
