import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SAMPLE_UUID = os.getenv("SAMPLE_UUID")
ALLOWED_ORIGINS = ["http://localhost:5173"]
