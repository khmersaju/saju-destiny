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
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.routers.fortune import router as fortune_router
from app.routers.fortune_v2 import router as fortune_v2_router
from app.routers.auth import router as auth_router

load_dotenv()

# /data 디렉토리 강제 생성 (Railway Volume 마운트 경로)
data_dir = Path("/data")
try:
    data_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"[STARTUP] /data directory ready: {data_dir.exists()}")
except Exception as e:
    logger.warning(f"[STARTUP] Could not create /data: {e}")

# DB_PATH 확인 로그
db_path = os.getenv("DB_PATH", "/data/users.db")
logger.info(f"[STARTUP] DB_PATH = {db_path}")
logger.info(f"[STARTUP] DB file exists = {Path(db_path).exists()}")

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
    db_path_val = os.getenv("DB_PATH", "/data/users.db")
    return {
        "status": "ok",
        "service": "ai-khmer-destiny-api",
        "version": "2.0.0",
        "db_path": db_path_val,
        "db_exists": Path(db_path_val).exists(),
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

@app.get("/privacy")
def privacy_policy():
    f = os.path.join(os.path.dirname(__file__), "static", "privacy.html")
    return FileResponse(f, media_type="text/html") if os.path.exists(f) else JSONResponse({}, status_code=404)

@app.get("/terms")
def terms_of_use():
    f = os.path.join(os.path.dirname(__file__), "static", "terms.html")
    return FileResponse(f, media_type="text/html") if os.path.exists(f) else JSONResponse({}, status_code=404)

@app.get("/.well-known/assetlinks.json")
def assetlinks():
    f = os.path.join(os.path.dirname(__file__), "static", ".well-known", "assetlinks.json")
    return FileResponse(f, media_type="application/json") if os.path.exists(f) else JSONResponse([], status_code=404)

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

@app.get("/s/{share_id}")
def share_page(share_id: str):
    """SNS 공유 링크 페이지 - DB에서 데이터 조회 + 풀이 텍스트 표시"""
    import json as _json, sqlite3 as _sqlite3
    from fastapi.responses import HTMLResponse
    DB_PATH_LOCAL = os.environ.get('DB_PATH', '/data/users.db')
    sdata = {}
    try:
        conn = _sqlite3.connect(DB_PATH_LOCAL)
        conn.row_factory = _sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM shares WHERE code=?", (share_id,))
        row = c.fetchone()
        conn.close()
        if row:
            sdata = dict(row)
            try: sdata['pillars'] = _json.loads(sdata.get('pillars') or '[]')
            except: sdata['pillars'] = []
            try: sdata['five_elements'] = _json.loads(sdata.get('five_elements') or '{}')
            except: sdata['five_elements'] = {}
    except Exception:
        sdata = {}

    name = sdata.get('name', 'Unknown')
    birth = sdata.get('birth', '')
    gender_raw = sdata.get('gender', 'male')
    gender_disp = 'ប្រុស' if gender_raw == 'male' else 'ស្រី'
    dominant = sdata.get('dominant', '')
    elem_map = {'\ubaa9': ('Wood', 'ឈើ', '#4CAF50'), '화': ('Fire', 'ភ្លើង', '#F44336'),
                '토': ('Earth', 'ដី', '#FF9800'), '금': ('Metal', 'ដែក', '#9E9E9E'), '수': ('Water', 'ទឹក', '#2196F3')}
    dom_en, dom_km, dom_color = elem_map.get(dominant, ('', '', '#fade4a'))
    pillars = sdata.get('pillars', [])
    five_el = sdata.get('five_elements', {})
    app_url = 'https://web-production-d0bd4.up.railway.app'

    # OG 메타 이미지 URL (공유 카드 이미지)
    og_img = f"{app_url}/api/v2/share-card-img/{share_id}"
    og_title = f"{name} ការ​ចែក​ជោគជតា​ក្នុង​ប្រព័ន្ធ​សាជូ"
    og_desc = f"ធាតុ​{dom_km} ({dom_en}) — {birth} · {gender_disp} | Saju Destiny ជោគជតា​ក្នុង​ប្រព័ន្ធ​សាជូ"

    # 필러 한자 카드 HTML
    pillar_labels = ['YEAR', 'MONTH', 'DAY', 'HOUR']
    pillar_html = ''
    elem_colors = {'\ubaa9':'#4CAF50','화':'#F44336','토':'#FF9800','금':'#9E9E9E','수':'#2196F3'}
    for i, p in enumerate(pillars[:4]):
        lbl = pillar_labels[i] if i < len(pillar_labels) else ''
        stem = p.get('stem', '')
        branch = p.get('branch', '')
        elem = p.get('element', '')
        ecolor = elem_colors.get(elem, '#fade4a')
        elem_en = elem_map.get(elem, (elem,'',''))[0]
        pillar_html += f'''
        <div style="background:rgba(255,255,255,0.08);border-radius:10px;padding:10px 8px;text-align:center;flex:1">
          <div style="font-size:9px;color:#8a9ab8;margin-bottom:4px">{lbl}</div>
          <div style="font-size:26px;font-weight:700;color:#fff;line-height:1">{stem}</div>
          <div style="font-size:22px;color:#ccc;line-height:1.2">{branch}</div>
          <div style="font-size:9px;color:{ecolor};margin-top:4px;font-weight:600">{elem_en}</div>
        </div>'''

    # 오행 바 HTML
    elem_order = [('목','Wood','ឈើ','#4CAF50'),('화','Fire','ភ្លើង','#F44336'),('토','Earth','ដី','#FF9800'),('금','Metal','ដែក','#9E9E9E'),('수','Water','ទឹក','#2196F3')]
    max_val = max(five_el.values()) if five_el else 1
    elem_html = ''
    for ek, een, ekm, ec in elem_order:
        val = five_el.get(ek, 0)
        pct = int(val / max(max_val, 1) * 100) if max_val > 0 else 0
        elem_html += f'''
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <div style="font-size:11px;color:#ccc;width:42px;text-align:right">{ekm}</div>
          <div style="flex:1;height:8px;background:rgba(255,255,255,0.1);border-radius:4px;overflow:hidden">
            <div style="height:100%;width:{pct}%;background:{ec};border-radius:4px"></div>
          </div>
          <div style="font-size:11px;color:#fade4a;width:14px;text-align:center">{val}</div>
        </div>'''

    # 데이터 없으면 안내 페이지
    if not sdata.get('name'):
        not_found_html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Saju Destiny</title></head><body style="font-family:sans-serif;background:#01092b;color:#fff;text-align:center;padding:60px 20px">
        <div style="font-size:40px;margin-bottom:16px">✨</div>
        <div style="font-size:20px;font-weight:700;color:#fade4a;margin-bottom:8px">Saju Destiny</div>
        <div style="font-size:14px;color:#8a9ab8;margin-bottom:32px">This share link has expired or does not exist.</div>
        <a href="{app_url}" style="background:#fade4a;color:#01092b;padding:14px 32px;border-radius:14px;font-weight:700;text-decoration:none;font-size:14px">Check My Destiny</a>
        </body></html>"""
        return HTMLResponse(content=not_found_html)

    # 풀이 텍스트 섹션 HTML
    reading_text = sdata.get('reading_text', '')
    mode_label_map = {
        'lifetime': 'Destiny Reading',
        'yearly': 'Yearly Fortune',
        'monthly': 'Monthly Fortune',
        'daily': 'Daily Fortune',
        'compatibility': 'Compatibility',
        'lucky_days': 'Lucky Days',
        'lucky_profile': 'Lucky Profile'
    }
    mode_label = mode_label_map.get(sdata.get('mode',''), 'Fortune Reading')
    reading_html = ''
    if reading_text:
        import re as _re
        clean = _re.sub(r'#{1,3}\s*', '', reading_text)
        clean = _re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#fade4a">\1</strong>', clean)
        clean = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', clean)
        paragraphs = [p.strip() for p in clean.split('\n') if p.strip()]
        paras_html = ''.join(f'<p style="margin-bottom:12px;line-height:1.8;font-size:14px;color:#e0e6f0">{p}</p>' for p in paragraphs)
        reading_html = f'''
        <div style="background:rgba(255,255,255,0.06);border-radius:14px;padding:20px;margin:16px 0">
          <div style="font-size:11px;font-weight:700;color:#fade4a;letter-spacing:1.5px;margin-bottom:14px">✨ {mode_label.upper()}</div>
          {paras_html}
        </div>'''

    html = f"""<!DOCTYPE html>
<html lang="km">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{og_title}</title>
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:image" content="{og_img}">
<meta property="og:url" content="{app_url}/s/{share_id}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<link href="https://fonts.googleapis.com/css2?family=Battambang:wght@400;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Battambang',sans-serif;background:#01092b;min-height:100vh;color:#e0e6f0}}
.wrap{{max-width:480px;margin:0 auto;padding-bottom:40px}}
.hero{{background:linear-gradient(135deg,#01092b,#1a0a3a);padding:28px 20px 24px;text-align:center}}
.hero-badge{{display:inline-block;background:rgba(250,222,74,0.15);border:1px solid rgba(250,222,74,0.4);border-radius:20px;padding:4px 14px;font-size:11px;color:#fade4a;margin-bottom:12px;letter-spacing:1px}}
.hero-name{{font-size:22px;font-weight:700;color:#fade4a;margin-bottom:4px}}
.hero-meta{{font-size:13px;color:#8a9ab8;margin-bottom:16px}}
.card{{background:rgba(255,255,255,0.06);border-radius:14px;padding:16px;margin:0 16px}}
.pillars{{display:flex;gap:8px;margin-bottom:14px}}
.dom-elem{{text-align:center;margin-top:12px;padding:10px;background:rgba(250,222,74,0.1);border-radius:10px;border:1px solid rgba(250,222,74,0.2)}}
.dom-label{{font-size:10px;color:#8a9ab8;margin-bottom:4px}}
.dom-val{{font-size:16px;font-weight:700}}
.reading-wrap{{padding:0 16px;margin-top:16px}}
.actions{{padding:16px;display:flex;gap:10px;margin-top:8px}}
.btn{{flex:1;padding:14px;border-radius:14px;font-size:14px;font-weight:700;cursor:pointer;border:none;text-align:center;text-decoration:none;display:block}}
.btn-primary{{background:#fade4a;color:#01092b}}
.btn-secondary{{background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.2)}}
.footer{{background:rgba(0,0,0,0.3);color:#fff;text-align:center;padding:20px 16px;margin-top:8px}}
.footer-title{{font-size:14px;font-weight:700;color:#fade4a;margin-bottom:4px}}
.footer-sub{{font-size:11px;color:#8a9ab8}}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
  <div class="hero-badge">ជោគជតា​សាជូ · SAJU DESTINY · Cambodia</div>
  <div class="hero-name">{name}</div>
  <div class="hero-meta">{birth} · {gender_disp}</div>
</div>
<div style="height:16px"></div>
<div class="card">
  <div class="pillars">{pillar_html}</div>
  {elem_html}
  <div class="dom-elem">
    <div class="dom-label">Dominant Element · ធាតុ​ស្ថាន​ខ្លាញ</div>
    <div class="dom-val" style="color:{dom_color}">{dom_en} · {dom_km}</div>
  </div>
</div>
<div class="reading-wrap">{reading_html}</div>
<div class="actions">
  <a href="{app_url}" class="btn btn-primary">🔮 Check My Destiny</a>
  <a href="{app_url}" class="btn btn-secondary">✨ Open App</a>
</div>
<div class="footer">
  <div class="footer-title">Saju Destiny · Cambodia</div>
  <div class="footer-sub">Traditional Four Pillars Destiny Reading for Cambodians</div>
</div>
</div>
</body></html>"""
    return HTMLResponse(content=html)

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    # API/시스템 경로는 제외
    skip = ("api/", "docs", "redoc", "health", "openapi.json", "static/", ".well-known", "privacy", "terms", "s/")
    if any(full_path.startswith(s) for s in skip):
        return JSONResponse({"error": "Not found"}, status_code=404)
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(index) if os.path.exists(index) else JSONResponse({"error": "Not found"}, status_code=404)
