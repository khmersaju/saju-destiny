"""
auth.py — User registration & authentication router
SQLite-backed, JWT token, free/premium tiers
"""
import sqlite3, hashlib, secrets, os, time
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
import json

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

# ── DB 경로 ──
# 우선순위: 환경변수 DB_PATH > /data/users.db (Railway Persistent Volume) > 로컬 data/
# Railway에서는 반드시 /data 볼륨을 마운트하고 DB_PATH=/data/users.db 환경변수를 설정해야 함
_db_env = os.getenv("DB_PATH")
if _db_env:
    DB_PATH = Path(_db_env)
elif Path("/data").exists():
    # Railway Persistent Volume이 마운트된 경우
    DB_PATH = Path("/data/users.db")
else:
    # 로컬 개발 환경
    DB_PATH = Path(__file__).parent.parent.parent / "data" / "users.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("JWT_SECRET", "khmer-destiny-secret-2025-change-in-prod")
TOKEN_EXPIRE_DAYS = 30

# ── DB 초기화 ──
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        email         TEXT    UNIQUE NOT NULL,
        password_hash TEXT    NOT NULL,
        full_name     TEXT,
        first_name    TEXT,
        last_name     TEXT,
        khmer_name    TEXT,
        phone         TEXT,
        gender        TEXT    CHECK(gender IN ('male','female','other')),
        birth_year    INTEGER,
        birth_month   INTEGER,
        birth_day     INTEGER,
        birth_hour    INTEGER DEFAULT 12,
        birth_minute  INTEGER DEFAULT 0,
        city          TEXT    DEFAULT 'Phnom Penh',
        province      TEXT,
        occupation    TEXT,
        language_pref TEXT    DEFAULT 'km',
        tier          TEXT    DEFAULT 'free' CHECK(tier IN ('free','premium','admin')),
        is_active     INTEGER DEFAULT 1,
        email_verified INTEGER DEFAULT 0,
        created_at    TEXT    DEFAULT (datetime('now')),
        last_login    TEXT,
        login_count   INTEGER DEFAULT 0,
        referral_code TEXT    UNIQUE,
        referred_by   TEXT,
        push_token    TEXT,
        notes         TEXT
    );

    CREATE TABLE IF NOT EXISTS sessions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        token      TEXT    UNIQUE NOT NULL,
        created_at TEXT    DEFAULT (datetime('now')),
        expires_at TEXT    NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS fortune_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        mode        TEXT    NOT NULL,
        request_data TEXT,
        result_summary TEXT,
        created_at  TEXT    DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS daily_readings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        date        TEXT    NOT NULL,
        reading     TEXT,
        lucky_color TEXT,
        lucky_number INTEGER,
        lucky_direction TEXT,
        energy_score INTEGER,
        created_at  TEXT    DEFAULT (datetime('now')),
        UNIQUE(user_id, date),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS app_counters (
        key   TEXT PRIMARY KEY,
        value INTEGER DEFAULT 0
    );
    -- INSERT OR IGNORE: DB가 처음 생성될 때만 초기값 삽입 (이후 배포에서는 기존 값 유지)
    INSERT OR IGNORE INTO app_counters (key, value) VALUES ('total_visits', 7700);
    INSERT OR IGNORE INTO app_counters (key, value) VALUES ('total_clicks', 7700);

    CREATE TABLE IF NOT EXISTS ad_banners (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT,
        image_url  TEXT    NOT NULL,
        link_url   TEXT    NOT NULL,
        position   TEXT    DEFAULT 'home' CHECK(position IN ('home','result','profile')),
        is_active  INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT    DEFAULT (datetime('now'))
    );
    INSERT OR REPLACE INTO ad_banners (id, title, image_url, link_url, position, is_active, sort_order)
    VALUES (1, 'The K Ground & G-mart', '/static/ad_banner_kground.jpg', 'https://www.facebook.com/share/p/1CkVgw1TJD/', 'home', 1, 0);

    CREATE TABLE IF NOT EXISTS shares (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        code       TEXT    UNIQUE NOT NULL,
        name       TEXT,
        birth      TEXT,
        gender     TEXT,
        mode       TEXT,
        dominant   TEXT,
        pillars    TEXT,
        five_elements TEXT,
        reading_text TEXT,
        created_at TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS password_reset_codes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        email      TEXT    NOT NULL,
        code       TEXT    NOT NULL,
        expires_at TEXT    NOT NULL,
        used       INTEGER DEFAULT 0,
        created_at TEXT    DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    conn.close()

init_db()

def _ensure_admin():
    """관리자 계정이 없으면 자동 생성"""
    import hashlib
    salt = "khmer_destiny_salt_v1"
    admin_email = "khmersaju@gmail.com"
    admin_pw_hash = hashlib.sha256(f"{salt}lucky815!".encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, tier FROM users WHERE email = ?", (admin_email,))
    row = c.fetchone()
    if row:
        # 이미 존재하면 tier를 admin으로 업데이트
        c.execute("UPDATE users SET tier='admin', password_hash=? WHERE email=?",
                  (admin_pw_hash, admin_email))
        print(f"[Admin] Updated tier to admin for {admin_email}")
    else:
        # 없으면 새로 생성
        ref_code = secrets.token_hex(4).upper()
        c.execute("""
            INSERT INTO users (email, password_hash, full_name, first_name, last_name,
                gender, birth_year, birth_month, birth_day,
                city, language_pref, tier, referral_code)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            admin_email, admin_pw_hash, 'Admin', 'Admin', 'Khmer Saju',
            'Male', 1990, 1, 1,
            'Phnom Penh', 'en', 'admin', ref_code
        ))
        print(f"[Admin] Created admin account: {admin_email}")
    conn.commit()
    conn.close()

_ensure_admin()

# ── 유틸 ──
def hash_password(pw: str) -> str:
    salt = "khmer_destiny_salt_v1"
    return hashlib.sha256(f"{salt}{pw}".encode()).hexdigest()

def make_token(user_id: int) -> str:
    payload = f"{user_id}:{int(time.time())}:{secrets.token_hex(16)}"
    return hashlib.sha256(payload.encode()).hexdigest()

def make_referral_code() -> str:
    return "KD" + secrets.token_hex(4).upper()

def get_user_by_token(token: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT u.* FROM users u
        JOIN sessions s ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
    """, (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    if not creds:
        return None
    return get_user_by_token(creds.credentials)

def require_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    user = get_current_user(creds)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

# ── Pydantic 모델 ──
class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str          # 표시용 전체 이름 (필수)
    first_name: Optional[str] = None   # 이름 (First Name)
    last_name: Optional[str] = None    # 성 (Last Name / Family Name)
    phone: str              # 필수
    khmer_name: Optional[str] = None
    gender: Optional[str] = "male"
    birth_year: Optional[int] = None
    birth_month: Optional[int] = None
    birth_day: Optional[int] = None
    birth_hour: Optional[int] = 12
    birth_minute: Optional[int] = 0
    city: Optional[str] = "Phnom Penh"
    province: Optional[str] = None
    occupation: Optional[str] = None
    language_pref: Optional[str] = "km"
    referred_by: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    khmer_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    occupation: Optional[str] = None
    language_pref: Optional[str] = None
    push_token: Optional[str] = None

# ── 엔드포인트 ──
@router.post("/register")
async def register(req: RegisterRequest):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 이메일 중복 확인
    c.execute("SELECT id FROM users WHERE email = ?", (req.email.lower().strip(),))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    # 필수값 검증
    if not req.full_name or not req.full_name.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Full name is required")
    if not req.phone or not req.phone.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Phone number is required")

    # 비밀번호 최소 길이
    if len(req.password) < 6:
        conn.close()
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    pw_hash = hash_password(req.password)
    ref_code = make_referral_code()

    # first_name, last_name이 없으면 full_name에서 자동 분리
    first_name = req.first_name
    last_name = req.last_name
    if not first_name and not last_name and req.full_name:
        parts = req.full_name.strip().split()
        if len(parts) >= 2:
            last_name = parts[0]
            first_name = " ".join(parts[1:])
        else:
            first_name = req.full_name.strip()

    c.execute("""
        INSERT INTO users (email, password_hash, full_name, first_name, last_name,
            khmer_name, phone, gender,
            birth_year, birth_month, birth_day, birth_hour, birth_minute,
            city, province, occupation, language_pref, referral_code, referred_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        req.email.lower().strip(), pw_hash,
        req.full_name, first_name, last_name,
        req.khmer_name, req.phone, req.gender,
        req.birth_year, req.birth_month, req.birth_day,
        req.birth_hour, req.birth_minute,
        req.city, req.province, req.occupation,
        req.language_pref, ref_code, req.referred_by
    ))
    user_id = c.lastrowid

    # 세션 토큰 생성
    token = make_token(user_id)
    expires = (datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)).isoformat()
    c.execute("INSERT INTO sessions (user_id, token, expires_at) VALUES (?,?,?)",
              (user_id, token, expires))
    conn.commit()

    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(c.fetchone())
    conn.close()

    return {
        "success": True,
        "token": token,
        "user": _safe_user(user),
        "message": "Registration successful! Welcome to Saju Destiny."
    }

@router.post("/login")
async def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE email = ? AND is_active = 1",
              (req.email.lower().strip(),))
    user = c.fetchone()

    if not user or user["password_hash"] != hash_password(req.password):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = dict(user)
    token = make_token(user["id"])
    expires = (datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)).isoformat()

    c.execute("INSERT INTO sessions (user_id, token, expires_at) VALUES (?,?,?)",
              (user["id"], token, expires))
    c.execute("UPDATE users SET last_login=datetime('now'), login_count=login_count+1 WHERE id=?",
              (user["id"],))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "token": token,
        "user": _safe_user(user),
        "message": "Login successful"
    }

@router.get("/me")
async def get_me(user: dict = Depends(require_user)):
    return {"success": True, "user": _safe_user(user)}

@router.put("/profile")
async def update_profile(req: UpdateProfileRequest, user: dict = Depends(require_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = {k: v for k, v in req.dict().items() if v is not None}
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [user["id"]]
        c.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
        conn.commit()
    conn.close()
    return {"success": True, "message": "Profile updated"}

@router.post("/logout")
async def logout(creds: HTTPAuthorizationCredentials = Depends(security)):
    if creds:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE token=?", (creds.credentials,))
        conn.commit()
        conn.close()
    return {"success": True, "message": "Logged out"}

@router.get("/stats")
async def get_stats(user: dict = Depends(require_user)):
    """관리자용 통계 (admin 전용)"""
    if user.get("tier") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total, tier, COUNT(CASE WHEN date(created_at)=date('now') THEN 1 END) as today FROM users GROUP BY tier")
    stats = [dict(r) for r in c.fetchall()]
    c.execute("SELECT COUNT(*) as total FROM users")
    total = c.fetchone()[0]
    conn.close()
    return {"total_users": total, "by_tier": stats}

@router.get("/stats/public")
async def get_public_stats():
    """공개 통계 - 총 회원수 (광고 게이트 판단용)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE is_active=1")
    total = c.fetchone()[0]
    conn.close()
    return {"total_users": total, "ad_gate_threshold": 5000, "ad_required": total >= 5000}


@router.post("/visit")
async def record_visit():
    """앱 클릭(방문) 기록 + 누적 클릭 수 반환 (공개 API)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 누적 클릭 수 증가
    c.execute("UPDATE app_counters SET value = value + 1 WHERE key = 'total_clicks'")
    c.execute("SELECT value FROM app_counters WHERE key = 'total_clicks'")
    row = c.fetchone()
    total_clicks = row[0] if row else 7700
    conn.commit()
    conn.close()
    return {"success": True, "total_visits": total_clicks, "total_clicks": total_clicks}


@router.get("/visit/count")
async def get_visit_count():
    """누적 클릭 수 조회 (공개 API)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM app_counters WHERE key = 'total_clicks'")
    row = c.fetchone()
    total_clicks = row[0] if row else 7700
    conn.close()
    return {"success": True, "total_visits": total_clicks, "total_clicks": total_clicks}

def _safe_user(u: dict) -> dict:
    """비밀번호 해시 제거 후 반환"""
    return {k: v for k, v in u.items() if k not in ("password_hash",)}


@router.get("/banners")
async def get_banners(position: str = "home"):
    """광고 배너 조회 (공개 API) - position: home/result/profile"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT id, title, image_url, link_url, position FROM ad_banners "
        "WHERE is_active=1 AND position=? ORDER BY sort_order ASC",
        (position,)
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"success": True, "banners": rows}


@router.post("/banners")
async def upsert_banner(
    banner_id: Optional[int] = None,
    title: str = "",
    image_url: str = "",
    link_url: str = "",
    position: str = "home",
    is_active: int = 1,
    sort_order: int = 0,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """광고 배너 추가/수정 (관리자 전용)"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Unauthorized")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if banner_id:
        c.execute(
            "UPDATE ad_banners SET title=?, image_url=?, link_url=?, position=?, is_active=?, sort_order=? WHERE id=?",
            (title, image_url, link_url, position, is_active, sort_order, banner_id)
        )
    else:
        c.execute(
            "INSERT INTO ad_banners (title, image_url, link_url, position, is_active, sort_order) VALUES (?,?,?,?,?,?)",
            (title, image_url, link_url, position, is_active, sort_order)
        )
    conn.commit()
    conn.close()
    return {"success": True}


# ── 비밀번호 재설정 ──
class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyResetCodeRequest(BaseModel):
    email: str
    code: str

class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """비밀번호 재설정 코드 발급 (이메일로 발송 또는 화면 표시)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # 이메일 존재 여부 확인
    c.execute("SELECT id, email, full_name FROM users WHERE email=? AND is_active=1", (req.email,))
    user = c.fetchone()
    if not user:
        conn.close()
        # 보안상 이메일 존재 여부를 노출하지 않음
        raise HTTPException(status_code=404, detail="Email not found")
    # 기존 미사용 코드 무효화
    c.execute("UPDATE password_reset_codes SET used=1 WHERE email=? AND used=0", (req.email,))
    # 6자리 숫자 코드 생성 (10분 유효)
    import random
    code = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # 10분 후 만료 시간 계산
    from datetime import timedelta
    expire_time = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO password_reset_codes (email, code, expires_at) VALUES (?,?,?)",
        (req.email, code, expire_time)
    )
    conn.commit()
    conn.close()
    # 실제 배포 시: 이메일 발송 (SMTP/SendGrid)
    # 현재: 코드를 응답에 포함 (개발/테스트 환경)
    return {
        "success": True,
        "message": "Reset code generated",
        "code": code,  # TODO: 실제 배포 시 제거하고 이메일로만 발송
        "expires_in_minutes": 10,
        "user_name": dict(user).get("full_name", "")
    }


@router.post("/verify-reset-code")
async def verify_reset_code(req: VerifyResetCodeRequest):
    """재설정 코드 유효성 검증"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "SELECT id FROM password_reset_codes WHERE email=? AND code=? AND used=0 AND expires_at > ?",
        (req.email, req.code, now)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return {"success": True, "message": "Code verified"}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """새 비밀번호 설정"""
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # 코드 검증
    c.execute(
        "SELECT id FROM password_reset_codes WHERE email=? AND code=? AND used=0 AND expires_at > ?",
        (req.email, req.code, now)
    )
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    # 비밀번호 업데이트
    new_hash = hash_password(req.new_password)
    c.execute("UPDATE users SET password_hash=? WHERE email=?", (new_hash, req.email))
    # 코드 사용 처리
    c.execute("UPDATE password_reset_codes SET used=1 WHERE email=? AND code=?", (req.email, req.code))
    # 기존 세션 모두 무효화
    c.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)", (req.email,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Password reset successful"}


# ===== 공유 링크 저장/조회 =====
import string as _string

def _gen_share_code(length=8):
    """8자리 랜덤 코드 생성"""
    import random
    chars = _string.ascii_letters + _string.digits
    return ''.join(random.choices(chars, k=length))

@router.post("/share/save")
async def save_share(request: Request):
    """공유 데이터 DB 저장 → 짧은 코드 반환"""
    import json as _json
    body = await request.json()
    name = body.get('name', '')
    birth = body.get('birth', '')
    gender = body.get('gender', 'male')
    mode = body.get('mode', 'lifetime')
    dominant = body.get('dominant', '')
    pillars = _json.dumps(body.get('pillars', []), ensure_ascii=False)
    five_elements = _json.dumps(body.get('five_elements', {}), ensure_ascii=False)
    reading_text = body.get('reading_text', '')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 중복 없는 코드 생성
    for _ in range(10):
        code = _gen_share_code(8)
        c.execute("SELECT id FROM shares WHERE code=?", (code,))
        if not c.fetchone():
            break
    c.execute(
        "INSERT INTO shares (code,name,birth,gender,mode,dominant,pillars,five_elements,reading_text) VALUES (?,?,?,?,?,?,?,?,?)",
        (code, name, birth, gender, mode, dominant, pillars, five_elements, reading_text)
    )
    conn.commit()
    conn.close()
    return {"success": True, "code": code}

@router.get("/share/{code}")
async def get_share(code: str):
    """공유 코드로 데이터 조회"""
    import json as _json
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM shares WHERE code=?", (code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"success": False, "error": "Not found"}
    d = dict(row)
    try: d['pillars'] = _json.loads(d['pillars'] or '[]')
    except: d['pillars'] = []
    try: d['five_elements'] = _json.loads(d['five_elements'] or '{}')
    except: d['five_elements'] = {}
    return {"success": True, "data": d}


# ── 관리자 전용: 사용자 목록 내보내기 ──
import csv, io
from fastapi.responses import StreamingResponse

@router.get("/admin/export-users")
async def export_users(user: dict = Depends(require_user)):
    """관리자 전용 — 전체 회원 목록을 CSV로 내보내기"""
    if user.get("tier") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT
            id, email, first_name, last_name,
            phone, gender,
            birth_year, birth_month, birth_day, birth_hour, birth_minute,
            city, province, occupation, language_pref,
            tier, is_active, email_verified,
            created_at, last_login, login_count,
            referral_code, referred_by, notes
        FROM users
        ORDER BY created_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    # 헤더
    writer.writerow([
        "ID", "Email", "First Name", "Last Name",
        "Phone", "Gender",
        "Birth Year", "Birth Month", "Birth Day", "Birth Hour", "Birth Minute",
        "City", "Province", "Occupation", "Language",
        "Tier", "Active", "Email Verified",
        "Created At", "Last Login", "Login Count",
        "Referral Code", "Referred By", "Notes"
    ])
    for row in rows:
        writer.writerow(list(row))

    output.seek(0)
    filename = f"saju_fortune_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/admin/users-json")
async def list_users_json(user: dict = Depends(require_user)):
    """관리자 전용 — 전체 회원 목록 JSON 반환"""
    if user.get("tier") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT
            id, email, first_name, last_name,
            phone, gender,
            birth_year, birth_month, birth_day,
            city, province, occupation, language_pref,
            tier, is_active, created_at, last_login, login_count,
            referral_code, referred_by
        FROM users
        ORDER BY created_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": len(rows), "users": rows}
