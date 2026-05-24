"""
AI Khmer Destiny - FastAPI Backend Server
Saju (Four Pillars of Destiny) AI Fortune App for Cambodia
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os

from app.routers.fortune import router as fortune_router
from app.routers.fortune_v2 import router as fortune_v2_router
from app.routers.auth import router as auth_router

load_dotenv()

app = FastAPI(
    title="AI Khmer Destiny API",
    version="2.0.0",
    description=(
        "Saju (Four Pillars of Destiny) AI Fortune App for Cambodia. "
        "Accurate Manseryeok calculation + AI-powered fortune analysis."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 설정
cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = ["*"] if cors_origins == "*" else [x.strip() for x in cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(fortune_router, prefix="/api/fortune", tags=["Fortune API v1"])
app.include_router(fortune_v2_router)   # v2: /api/v2/...
app.include_router(auth_router)         # auth: /api/v2/auth/...


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "ai-khmer-destiny-api",
        "version": "2.0.0",
        "features": [
            "Accurate Manseryeok calculation via sajupy",
            "Cambodia timezone (UTC+7) + longitude correction",
            "AI-powered fortune reports via OpenAI GPT",
            "User registration & authentication (free/premium)",
            "Five Elements analysis",
        ],
    }


# 정적 파일 서빙 (프론트엔드)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    # /static/ 경로로 정적 파일 직접 서빙 (이미지, CSS 등)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    icons_dir = os.path.join(static_dir, "icons")
    if os.path.exists(icons_dir):
        app.mount("/icons", StaticFiles(directory=icons_dir), name="icons")

@app.get("/manifest.json")
def manifest():
    f = os.path.join(os.path.dirname(__file__), "static", "manifest.json")
    return FileResponse(f) if os.path.exists(f) else JSONResponse({}, status_code=404)

@app.get("/sw.js")
def service_worker():
    f = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    return FileResponse(f, media_type="application/javascript") if os.path.exists(f) else JSONResponse({}, status_code=404)

@app.get("/")
def root():
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return JSONResponse({"message": "Welcome to AI Khmer Destiny API", "docs": "/docs"})

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    # API/시스템 경로는 제외
    skip = ("api/", "docs", "redoc", "health", "openapi.json", "static/")
    if any(full_path.startswith(s) for s in skip):
        return JSONResponse({"error": "Not found"}, status_code=404)
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(index) if os.path.exists(index) else JSONResponse({"error": "Not found"}, status_code=404)
