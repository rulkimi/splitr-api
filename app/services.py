from PIL import Image
import io
import json
from fastapi import UploadFile
from app.ai_model import get_ai_response
from app.prompt import create_analysis_prompt
from app.schemas import Receipt
import uuid
from fastapi import UploadFile
from app.config import SAMPLE_UUID

async def analyze_receipt(file: UploadFile):
  image_data = await file.read()
  image = Image.open(io.BytesIO(image_data))

  prompt = create_analysis_prompt()
  response = get_ai_response(contents=[prompt, image], response_schema=Receipt)
  return json.loads(response)

async def upload_file_to_supabase(supabase, file: UploadFile, bucket_name: str):
  try:
    if not file.content_type.startswith('image/'):
      return None, "File must be an image"
    
    file_content = await file.read()
    unique_filename = f"{SAMPLE_UUID}/{uuid.uuid4()}-{file.filename}"

    response = supabase.storage.from_(bucket_name).upload(unique_filename, file_content)
    
    if response:
      url = supabase.storage.from_(bucket_name).get_public_url(unique_filename)
      return url, None
    return None, "Failed to upload file to Supabase storage"
  except Exception as e:
      return None, str(e)