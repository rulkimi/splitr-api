from PIL import Image
import io
import json
from fastapi import UploadFile
from app.ai_model import get_ai_response
from app.prompt import create_analysis_prompt
from app.schemas import Receipt

async def analyze_receipt(file: UploadFile):
  image_data = await file.read()
  image = Image.open(io.BytesIO(image_data))

  prompt = create_analysis_prompt()
  response = get_ai_response(contents=[prompt, image], response_schema=Receipt)
  return json.loads(response)

