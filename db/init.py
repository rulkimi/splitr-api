import os
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_KEY

def create_supabase_client():
    url: str = SUPABASE_URL
    key: str = SUPABASE_KEY
    supabase: Client = create_client(url, key)
    return supabase
