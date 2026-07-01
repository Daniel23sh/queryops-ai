from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.responses import ApiError, api_error_handler
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.query_templates import router as query_templates_router
from app.api.routes.role_requests import router as role_requests_router
from app.core.config import FRONTEND_DEV_ORIGINS

app = FastAPI(title="QueryOps AI Backend")
app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(query_templates_router)
app.include_router(role_requests_router)
