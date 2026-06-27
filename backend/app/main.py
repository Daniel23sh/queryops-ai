from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.core.config import FRONTEND_DEV_ORIGINS

app = FastAPI(title="QueryOps AI Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_DEV_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(health_router)
