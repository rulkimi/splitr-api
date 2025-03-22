from fastapi import FastAPI
from app.middleware import add_cors_middleware
from app.routes import router

app = FastAPI(title="Receipt Analysis API")

add_cors_middleware(app)
app.include_router(router)
