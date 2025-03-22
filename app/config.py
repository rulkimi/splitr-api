import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ALLOWED_ORIGINS = ["http://localhost:5173"]
