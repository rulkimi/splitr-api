from google import genai
from app.config import GOOGLE_API_KEY

client = genai.Client(api_key=GOOGLE_API_KEY)

def get_ai_response(contents, response_schema=None):
  response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=contents,
    config={
      'response_mime_type': 'application/json',
      **({"response_schema": response_schema} if response_schema is not None else {})
    }
  )
  return response.text