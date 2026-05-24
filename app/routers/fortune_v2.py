"""
AI Khmer Destiny — FastAPI 라우터 v2
모든 운세 API 엔드포인트
"""
from __future__ import annotations
import os
import sqlite3
import hashlib
import json
from pathlib import Path
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv

# ─── 운세 풀이 영구 DB 캐시 (서버 재시작 후에도 동일한 결과 보장) ───
_FORTUNE_CACHE: dict[str, str] = {}  # 인메모리 1차 캐시 (빠른 조회)
_DB_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "fortune_cache.db"
_DB_CACHE_PATH.parent.mkdir(exist_ok=True)

def _init_cache_db():
    """영구 캐시 DB 초기화"""
    conn = sqlite3.connect(str(_DB_CACHE_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fortune_cache (
            cache_key  TEXT PRIMARY KEY,
            language   TEXT NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def _db_cache_get(cache_key: str) -> str | None:
    """DB에서 캐시 조회"""
    try:
        conn = sqlite3.connect(str(_DB_CACHE_PATH))
        row = conn.execute("SELECT text FROM fortune_cache WHERE cache_key=?", (cache_key,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

def _db_cache_set(cache_key: str, language: str, text: str):
    """DB에 캐시 저장"""
    try:
        conn = sqlite3.connect(str(_DB_CACHE_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO fortune_cache (cache_key, language, text) VALUES (?,?,?)",
            (cache_key, language, text)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

# 앱 시작 시 캐시 DB 초기화
_init_cache_db()

from app.services.saju_engine_v2 import (
    calculate_full_chart, calculate_daeun, calculate_seun,
    calculate_wolun, calculate_ilun, find_lucky_days,
    calculate_compatibility, calculate_life_stages,
    solar_to_lunar,
    ELEMENT_EN, ELEMENT_ICON, ELEMENT_COLOR,
    STEM_KR, BRANCH_KR, BRANCH_EN,
)

router = APIRouter(prefix="/api/v2", tags=["fortune-v2"])

# OpenAI 클라이언트
def _get_client():
    load_dotenv(override=True)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4.1-mini")


# ─── 요청/응답 모델 ────────────────────────────────────────────────
class BirthInput(BaseModel):
    name: str = Field(default="", description="이름")
    birth_year: int = Field(..., ge=1900, le=2010)
    birth_month: int = Field(..., ge=1, le=12)
    birth_day: int = Field(..., ge=1, le=31)
    birth_hour: Optional[int] = Field(default=12, ge=0, le=23)
    birth_minute: int = Field(default=0, ge=0, le=59, description="0 또는 30 (30분 단위)")
    gender: str = Field(default="male", pattern="^(male|female)$")
    city: str = Field(default="Phnom Penh")
    language: str = Field(default="en", description="en/km (English/Khmer)")


class CompatibilityInput(BaseModel):
    person_a: BirthInput
    person_b: BirthInput
    language: str = Field(default="en")


class LuckyDaysInput(BaseModel):
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int = 12
    birth_minute: int = 0
    gender: str = "male"
    city: str = "Phnom Penh"
    target_year: Optional[int] = None
    target_month: Optional[int] = None


class DailyFortuneInput(BaseModel):
    birth_year: int
    birth_month: int
    birth_day: int
    birth_hour: int = 12
    birth_minute: int = 0
    gender: str = "male"
    city: str = "Phnom Penh"
    target_date: Optional[str] = None  # YYYY-MM-DD
    language: str = Field(default="en", description="en/km")


# ─── 운세 텍스트 생성 (결정론적 캐싱) ──────────────────────────────────
def _make_cache_key(prompt: str, language: str) -> str:
    """입력값 기반 캐시 키 생성 (동일 입력 = 동일 키)"""
    raw = json.dumps({"prompt": prompt, "lang": language}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _ai_fortune(prompt: str, max_tokens: int = 600, language: str = "en") -> str:
    """
    사주 풀이 텍스트 생성.
    ① 동일 입력값이면 캐시에서 즉시 반환 (완전 동일한 내용 보장)
    ② 영어로 먼저 생성 (temperature=0 완전 결정론적)
    ③ km 요청 시 영어 풀이를 크메르어로 번역 (temperature=0)
    
    NOTE: 크메르어 유니코드 문자는 영어 대비 토큰 소비가 약 2.5~3배 많음.
    번역 max_tokens = 영어 max_tokens * 3.0 으로 설정하여 잘림 방지.
    """
    global _FORTUNE_CACHE

    # ① 캐시 확인: 동일 입력이면 즉시 반환
    cache_key = _make_cache_key(prompt, language)
    # 1새 인메모리 캐시 확인 (빠름)
    if cache_key in _FORTUNE_CACHE:
        return _FORTUNE_CACHE[cache_key]
    # 2새 DB 영구 캐시 확인 (서버 재시작 후에도 유지)
    db_cached = _db_cache_get(cache_key)
    if db_cached:
        _FORTUNE_CACHE[cache_key] = db_cached  # 인메모리에도 올려놓기
        return db_cached

    system_en = (
        "You are a master Saju (Four Pillars of Destiny) fortune teller "
        "with deep knowledge of Cambodian culture and the Khmer way of life. "
        "You interpret destiny through the ancient principles of the Four Pillars, "
        "Five Elements (Wood, Fire, Earth, Metal, Water), Yin-Yang balance, "
        "and the 60-year Sexagenary cycle. "
        "Your readings are warm, insightful, practical, and culturally respectful. "
        "IMPORTANT: Do NOT reference any specific religion, religious figures, "
        "temples, prayers, or religious practices (including Buddhism, Christianity, Islam, etc.). "
        "Focus only on natural cosmic principles, elemental balance, and practical life guidance. "
        "Always provide actionable advice relevant to Cambodian daily life "
        "(career, relationships, health, finances). "
        "Write your entire response in clear, accessible English."
    )

    # 크메르어 병기 번역 시 사용할 전문용어 대응표
    SAJU_TERMS_BILINGUAL = (
        "IMPORTANT BILINGUAL GLOSSARY — when you translate, keep these English terms "
        "and add the Khmer explanation in parentheses right after each term:\n"
        "Four Pillars → Four Pillars (សសរទាំង ៤) | "
        "Day Master → Day Master (អ្នកគ្រប់ក្រង) | "
        "Five Elements → Five Elements (ធាតុ ៥) | "
        "Wood → Wood (ឈើ) | Fire → Fire (ភ្លើង) | "
        "Earth → Earth (ដី) | Metal → Metal (លោហ) | Water → Water (ទឹក) | "
        "Yin → Yin (យឹន) | Yang → Yang (យាង) | "
        "Rat → Rat (កណ្ដុរ) | Ox → Ox (គោ) | Tiger → Tiger (ខ្លា) | "
        "Rabbit → Rabbit (ទន្សាយ) | Dragon → Dragon (នាគ) | Snake → Snake (ពស់) | "
        "Horse → Horse (សេះ) | Goat → Goat (ពពែ) | Monkey → Monkey (ស្វា) | "
        "Rooster → Rooster (មាន់) | Dog → Dog (ឆ្កែ) | Pig → Pig (ជ្រូក) | "
        "Sexagenary cycle → Sexagenary cycle (វត្ត ៦០ ឆ្នាំ) | "
        "Fortune → Fortune (ជោគជតា) | Destiny → Destiny (វាសនា) | "
        "Lucky → Lucky (មង្គល) | Auspicious → Auspicious (សុប័រមង្គល)"
    )

    try:
        c = _get_client()

        # ② 영어 풀이 생성 — temperature=0 으로 완전 결정론적
        # 동일 프롬프트 = 동일 결과 보장
        resp_en = c.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_en},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0,   # ★ 결정론적: 동일 입력 = 동일 출력
            seed=42,          # ★ 추가 안전장치: seed 고정
        )
        english_text = resp_en.choices[0].message.content.strip()

        if language != "km":
            # 영어 결과 인메모리 + DB 영구 캐시 저장
            _FORTUNE_CACHE[cache_key] = english_text
            _db_cache_set(cache_key, language, english_text)
            return english_text

        # ③ 크메르어 번역 — temperature=0 으로 완전 결정론적
        # 영어 전문용어는 유지하고 크메르어 설명을 괄호 안에 병기
        translate_prompt = (
            f"{SAJU_TERMS_BILINGUAL}\n\n"
            f"Now translate the following fortune reading into natural, fluent Khmer (ភាសាខ្មែរ). "
            f"CRITICAL RULES:\n"
            f"1. Keep ALL English Saju terms (Four Pillars, Day Master, Wood, Fire, etc.) "
            f"and add the Khmer meaning in parentheses right after each term, "
            f"e.g. 'Wood (ឈើ)', 'Four Pillars (សសរទាំង ៤)', 'Rooster (មាន់)'.\n"
            f"2. Translate ALL other sentences fully into Khmer.\n"
            f"3. Maintain the EXACT same length, depth, and structure as the original.\n"
            f"4. NEVER truncate, summarize, or omit any part.\n"
            f"5. Keep the warm, encouraging tone.\n\n"
            f"Text to translate:\n{english_text}"
        )
        resp_km = c.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You are a professional bilingual Khmer-English translator specializing in Saju fortune texts. "
                    "Your task: translate sentences into Khmer, but KEEP English Saju technical terms "
                    "(like Four Pillars, Day Master, Wood, Fire, Earth, Metal, Water, Yin, Yang, zodiac animals) "
                    "and add their Khmer meaning in parentheses immediately after, e.g. 'Wood (ឈើ)'. "
                    "This bilingual format helps Cambodian readers understand both the English term and its Khmer meaning. "
                    "NEVER truncate or skip any sentences. Translate every paragraph completely."
                )},
                {"role": "user", "content": translate_prompt},
            ],
            max_tokens=int(max_tokens * 3.5),  # ★ 병기 형식으로 토큰 증가 → 3.5배 여유
            temperature=0,   # ★ 결정론적
            seed=42,
        )
        khmer_text = resp_km.choices[0].message.content.strip()

        # 크메르어 결과 인메모리 + DB 영구 캐시 저장
        _FORTUNE_CACHE[cache_key] = khmer_text
        _db_cache_set(cache_key, language, khmer_text)
        return khmer_text

    except Exception as e:
        return f"[Fortune reading temporarily unavailable: {str(e)[:60]}]"


def _build_chart_summary(chart: dict, name: str = "", gender: str = "male") -> str:
    """사주 차트 요약 텍스트 생성 (성별·개인화 포함)"""
    p = chart["pillars"]
    elem = chart["five_elements"]
    dm = chart["day_master"]
    animal = chart["animal_sign"]
    lunar = chart["lunar"]

    # 오행 강약 분석
    elem_vals = {
        'Wood': elem.get('\ubaa9', 0),
        'Fire': elem.get('\ud654', 0),
        'Earth': elem.get('\ud1a0', 0),
        'Metal': elem.get('\uae08', 0),
        'Water': elem.get('\uc218', 0),
    }
    total = sum(elem_vals.values()) or 1
    elem_pct = {k: round(v/total*100) for k, v in elem_vals.items()}
    elem_balance = ', '.join(f"{k}={v}%" for k, v in elem_pct.items())

    # 성별에 따른 역할 설명
    gender_label = "male" if gender == "male" else "female"
    gender_context = (
        "As a man, his destiny is shaped by ambition, career leadership, and providing for family."
        if gender == "male" else
        "As a woman, her destiny is shaped by intuition, nurturing relationships, and inner strength."
    )

    # 일간 음양 특성
    yin_yang_note = (
        "Yang Day Master: outward, active, assertive energy."
        if dm.get('yin_yang', '').lower() == 'yang' else
        "Yin Day Master: inward, receptive, intuitive energy."
    )

    # 오행 불균형 특이사항
    dominant_en = ELEMENT_EN.get(chart.get('dominant_element', ''), '')
    weak_en = ELEMENT_EN.get(chart.get('weak_element', ''), '')
    imbalance_note = ""
    if dominant_en and weak_en:
        imbalance_note = (
            f"Elemental Imbalance: Strong {dominant_en} energy (may cause overconfidence/excess), "
            f"Weak {weak_en} energy (needs cultivation to balance destiny)."
        )

    return (
        f"=== PERSONAL SAJU CHART ==="
        f"\nName: {name or 'Anonymous'}"
        f"\nGender: {gender_label.upper()} — {gender_context}"
        f"\nFour Pillars (Saju):"
        f"\n  Year Pillar: {p['year']['pillar']} ({p['year']['branch_en']} year, {ELEMENT_EN.get(p['year']['element'],'')} element)"
        f"\n  Month Pillar: {p['month']['pillar']} ({p['month']['branch_en']} month, {ELEMENT_EN.get(p['month']['element'],'')} element)"
        f"\n  Day Pillar: {p['day']['pillar']} ({p['day']['branch_en']} day, {ELEMENT_EN.get(p['day']['element'],'')} element)"
        f"\n  Hour Pillar: {p['hour']['pillar']} ({p['hour']['branch_en']} hour, {ELEMENT_EN.get(p['hour']['element'],'')} element)"
        f"\nDay Master: {dm['stem']} ({ELEMENT_EN.get(dm['element'],'')} element, {dm.get('yin_yang','')}) — {yin_yang_note}"
        f"\nFive Elements Balance: {elem_balance}"
        f"\nDominant Element: {dominant_en}"
        f"\nWeak Element: {weak_en}"
        f"\n{imbalance_note}"
        f"\nChinese Zodiac: {animal}"
        f"\nLunar Birth Date: {lunar['lunar_iso']} ({lunar.get('gapja_korean','')})"
        f"\n"
    )


# ─── 1. 기본 사주 차트 ────────────────────────────────────────────
@router.post("/chart")
async def get_chart(data: BirthInput):
    """사주 차트 계산 (AI 풀이 없음 — 무료)"""
    try:
        chart = calculate_full_chart(
            data.birth_year, data.birth_month, data.birth_day,
            data.birth_hour, data.birth_minute, data.gender, data.city
        )
        return {"success": True, "chart": chart}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 2. 전체운 (평생운) ───────────────────────────────────────────
@router.post("/lifetime")
async def get_lifetime_fortune(data: BirthInput):
    """평생운 + 초년/중년/말년 + AI 풀이"""
    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    daeun = calculate_daeun(data.birth_year, data.birth_month, data.birth_day, data.gender, chart)
    life_stages = calculate_life_stages(chart, data.birth_year)

    chart_summary = _build_chart_summary(chart, data.name, data.gender)
    # 성별에 따른 맞춤 프롬프트
    gender_focus = (
        "Focus on: career ambition, leadership roles, financial independence, "
        "marriage timing for a man, and how he can best provide for his family."
        if data.gender == "male" else
        "Focus on: intuitive strengths, relationship harmony, motherhood timing, "
        "career balance with family, and how she can best express her inner power."
    )
    prompt = (
        f"{chart_summary}\n"
        f"Life Stages:\n"
        f"  Early Life (0-30): {life_stages['early_life']['quality']} ({ELEMENT_EN.get(life_stages['early_life']['element'],'')} element, score {life_stages['early_life']['score']}/100)\n"
        f"  Mid Life (31-60): {life_stages['mid_life']['quality']} ({ELEMENT_EN.get(life_stages['mid_life']['element'],'')} element, score {life_stages['mid_life']['score']}/100)\n"
        f"  Late Life (61+): {life_stages['late_life']['quality']} ({ELEMENT_EN.get(life_stages['late_life']['element'],'')} element, score {life_stages['late_life']['score']}/100)\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus}\n\n"
        f"Please provide a comprehensive lifetime fortune reading for this specific person. "
        f"Make the reading UNIQUE to their exact Four Pillars combination — "
        f"do NOT give generic advice. Reference their specific Day Master element, "
        f"dominant/weak elements, and zodiac animal. "
        f"Include: core personality traits from their Day Master, career path aligned with their elements, "
        f"wealth potential, love and marriage (gender-appropriate), health tendencies, "
        f"and practical life advice for Cambodians. "
        f"Write in 4-5 paragraphs, warm and encouraging tone."
    )
    ai_text = _ai_fortune(prompt, max_tokens=1200, language=data.language)

    return {
        "success": True,
        "chart": chart,
        "life_stages": life_stages,
        "daeun": daeun,
        "ai_reading": ai_text,
        "tier": "free_preview",
    }


# ─── 3. 신년운세 ─────────────────────────────────────────────────
@router.post("/yearly")
async def get_yearly_fortune(data: BirthInput, year: int = None):
    """신년/세운 운세"""
    if year is None:
        year = date.today().year

    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    seun = calculate_seun(year, 1)[0]
    chart_summary = _build_chart_summary(chart, data.name, data.gender)
    gender_focus_yr = (
        "For this man: emphasize career advancement, business opportunities, "
        "financial growth, and relationship milestones in {year}."
        if data.gender == "male" else
        "For this woman: emphasize personal growth, relationship harmony, "
        "family wellbeing, and career-life balance in {year}."
    ).format(year=year)

    prompt = (
        f"{chart_summary}\n"
        f"Year {year} Fortune:\n"
        f"  Year Pillar: {seun['stem']}{seun['branch']} ({seun['animal']} year, {ELEMENT_EN.get(seun['element'],'')} element)\n"
        f"  Interaction with Day Master ({ELEMENT_EN.get(chart['day_master']['element'],'')}): "
        f"{'Supportive' if seun['element'] == chart['day_master']['element'] else 'Challenging'} energy\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_yr}\n\n"
        f"Please provide a detailed {year} yearly fortune reading UNIQUE to this person's chart. "
        f"Reference their specific Day Master and how the {seun['animal']} year energy interacts with it. "
        f"Cover: overall energy of the year, career & business opportunities, financial outlook, "
        f"love & relationships, health advice, and best months to take action. "
        f"Include Cambodian-specific advice (Khmer New Year timing, Pchum Ben, auspicious activities). "
        f"Write 4 paragraphs."
    )
    ai_text = _ai_fortune(prompt, max_tokens=1000, language=data.language)

    return {
        "success": True,
        "year": year,
        "year_pillar": seun,
        "chart": chart,
        "ai_reading": ai_text,
    }


# ─── 4. 월별 운세 ────────────────────────────────────────────────
@router.post("/monthly")
async def get_monthly_fortune(data: BirthInput, year: int = None):
    """12개월 월운"""
    if year is None:
        year = date.today().year

    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    # 일간 오행과 지배 오행을 전달하여 월별 점수 변별력 확보
    day_master_elem = chart.get("day_master", {}).get("element", "")
    dominant_elem = chart.get("dominant_element", "")
    wolun = calculate_wolun(year, day_master_elem=day_master_elem, dominant_elem=dominant_elem)
    chart_summary = _build_chart_summary(chart, data.name, data.gender)

    # 현재 월 + 다음 2개월 AI 풀이
    current_month = date.today().month
    months_to_read = wolun[current_month-1:current_month+2]
    months_text = "\n".join([
        f"  {m['month_name']}: {m['stem']}{m['branch']} ({ELEMENT_EN.get(m['element'],'')} element, score {m.get('score',65)}/100)"
        for m in months_to_read
    ])
    gender_focus_mo = (
        "For this man: focus on career moves, financial decisions, and relationship opportunities."
        if data.gender == "male" else
        "For this woman: focus on relationship dynamics, family harmony, and personal growth."
    )

    prompt = (
        f"{chart_summary}\n"
        f"Monthly Fortune for {year} (upcoming 3 months, with elemental scores):\n{months_text}\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_mo}\n\n"
        f"Provide a monthly fortune reading UNIQUE to this person's chart for each of these 3 months. "
        f"Reference how each month's element interacts with their Day Master element. "
        f"For each month: key theme, opportunities, cautions, and 1 specific lucky day. "
        f"Keep each month's reading to 2-3 sentences. "
        f"Include practical Cambodian life advice (business timing, travel, ceremonies)."
    )
    ai_text = _ai_fortune(prompt, max_tokens=900, language=data.language)

    return {
        "success": True,
        "year": year,
        "monthly_pillars": wolun,
        "chart": chart,
        "ai_reading": ai_text,
        "current_month": current_month,
    }


# ─── 5. 일별 운세 ────────────────────────────────────────────────
@router.post("/daily")
async def get_daily_fortune(data: DailyFortuneInput):
    """오늘/지정일 일운"""
    if data.target_date:
        try:
            target = date.fromisoformat(data.target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        target = date.today()

    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    ilun = calculate_ilun(target)
    chart_summary = _build_chart_summary(chart, gender=data.gender)
    gender_focus_day = (
        "For this man: give practical advice on work, finances, and social interactions today."
        if data.gender == "male" else
        "For this woman: give practical advice on relationships, family, and personal wellbeing today."
    )

    prompt = (
        f"{chart_summary}\n"
        f"Today's Date: {target.strftime('%B %d, %Y')}\n"
        f"Today's Day Pillar: {ilun['stem']}{ilun['branch']} ({ELEMENT_EN.get(ilun['element'],'')} element, {ilun['branch_en']} day)\n"
        f"Lunar Date: {ilun['lunar']['lunar_iso']}\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_day}\n\n"
        f"Provide a daily fortune reading UNIQUE to this person's chart for today. "
        f"Reference how today's {ELEMENT_EN.get(ilun['element'],'')} energy interacts with their Day Master. "
        f"Include: overall energy for today, best activities, cautions, lucky color and direction, "
        f"and a motivational message in Cambodian spirit. "
        f"Keep it concise (3 short paragraphs)."
    )
    ai_text = _ai_fortune(prompt, max_tokens=600, language=data.language)

    return {
        "success": True,
        "date": target.isoformat(),
        "day_pillar": ilun,
        "chart": chart,
        "ai_reading": ai_text,
        "lucky_color": chart["lucky"]["colors"],
        "lucky_direction": chart["lucky"]["direction"],
        "lucky_numbers": chart["lucky"]["numbers"],
    }


# ─── 6. 궁합 ─────────────────────────────────────────────────────
@router.post("/compatibility")
async def get_compatibility(data: CompatibilityInput):
    """두 사람의 사주 궁합 분석"""
    chart_a = calculate_full_chart(
        data.person_a.birth_year, data.person_a.birth_month, data.person_a.birth_day,
        data.person_a.birth_hour, data.person_a.birth_minute, data.person_a.gender, data.person_a.city
    )
    chart_b = calculate_full_chart(
        data.person_b.birth_year, data.person_b.birth_month, data.person_b.birth_day,
        data.person_b.birth_hour, data.person_b.birth_minute, data.person_b.gender, data.person_b.city
    )
    compat = calculate_compatibility(chart_a, chart_b)

    summary_a = _build_chart_summary(chart_a, data.person_a.name, data.person_a.gender)
    summary_b = _build_chart_summary(chart_b, data.person_b.name, data.person_b.gender)

    # 두 사람의 일간 오행 상호작용
    elem_a = ELEMENT_EN.get(chart_a['day_master']['element'], '')
    elem_b = ELEMENT_EN.get(chart_b['day_master']['element'], '')
    elem_interaction = (
        f"{data.person_a.name or 'Person A'}'s {elem_a} Day Master meets "
        f"{data.person_b.name or 'Person B'}'s {elem_b} Day Master."
    )

    prompt = (
        f"Person A ({data.person_a.gender.upper()}):\n{summary_a}\n"
        f"Person B ({data.person_b.gender.upper()}):\n{summary_b}\n"
        f"Compatibility Score: {compat['score']}/100\n"
        f"Relationship Type: {compat['relation']}\n"
        f"Elemental Interaction: {elem_interaction}\n\n"
        f"Provide a detailed compatibility reading UNIQUE to these two specific charts. "
        f"Reference their actual Day Master elements and how they interact (generate/control/neutral). "
        f"Include: overall compatibility based on their elements, emotional connection, communication style, "
        f"financial harmony, family life potential, and challenges to overcome. "
        f"Add Cambodian cultural perspective (family approval, auspicious wedding timing). "
        f"Write 4 paragraphs."
    )
    ai_text = _ai_fortune(prompt, max_tokens=1000, language=data.language)

    return {
        "success": True,
        "compatibility": compat,
        "chart_a": chart_a,
        "chart_b": chart_b,
        "ai_reading": ai_text,
    }


# ─── 7. 길일 찾기 ────────────────────────────────────────────────
@router.post("/lucky-days")
async def get_lucky_days(data: LuckyDaysInput):
    """해당 월의 길일 목록"""
    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    day_elem = chart["day_master"]["element"]
    lucky = find_lucky_days(
        day_elem,
        data.target_year or date.today().year,
        data.target_month or date.today().month,
        count=15
    )

    return {
        "success": True,
        "lucky_days": lucky,
        "day_master_element": day_elem,
        "day_master_element_en": ELEMENT_EN.get(day_elem, ""),
        "chart": chart,
        "tip": f"Days with {ELEMENT_EN.get(day_elem,'')} or supporting elements are most auspicious for you.",
    }


# ─── 8. 오행 색깔/방향/숫자 ──────────────────────────────────────
@router.post("/lucky-profile")
async def get_lucky_profile(data: BirthInput):
    """오행 기반 행운 프로필 (색깔, 방향, 숫자, 직업)"""
    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    dominant = chart["dominant_element"]
    chart_summary = _build_chart_summary(chart, data.name, data.gender)
    gender_focus_lp = (
        "For this man: suggest career paths with leadership potential, "
        "and how to use lucky elements in business and daily work."
        if data.gender == "male" else
        "For this woman: suggest career paths that balance ambition and harmony, "
        "and how to use lucky elements in home and relationships."
    )

    prompt = (
        f"{chart_summary}\n"
        f"Lucky Profile Request:\n"
        f"Dominant Element: {ELEMENT_EN.get(dominant,'')}\n"
        f"Lucky Colors: {chart['lucky']['colors']['en']}\n"
        f"Lucky Direction: {chart['lucky']['direction']['en']}\n"
        f"Lucky Numbers: {chart['lucky']['numbers']}\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_lp}\n\n"
        f"Provide a personalized lucky profile UNIQUE to this person's exact chart. "
        f"Explain WHY these specific colors, directions, and numbers are lucky based on their Day Master. "
        f"Give practical daily life tips for Cambodians: "
        f"home decoration colors, which direction to face when working, "
        f"lucky numbers for business, and best career paths aligned with their elements. "
        f"Write 3 paragraphs."
    )
    ai_text = _ai_fortune(prompt, max_tokens=800, language=data.language)

    return {
        "success": True,
        "chart": chart,
        "lucky_profile": {
            "dominant_element": dominant,
            "dominant_element_en": ELEMENT_EN.get(dominant, ""),
            "dominant_element_icon": ELEMENT_ICON.get(dominant, ""),
            "dominant_element_color": ELEMENT_COLOR.get(dominant, ""),
            "weak_element": chart["weak_element"],
            "weak_element_en": ELEMENT_EN.get(chart["weak_element"], ""),
            "lucky_colors": chart["lucky"]["colors"],
            "lucky_direction": chart["lucky"]["direction"],
            "lucky_numbers": chart["lucky"]["numbers"],
            "lucky_careers": chart["lucky"]["careers"],
        },
        "ai_reading": ai_text,
    }


# ─── 9. 대운 상세 ────────────────────────────────────────────────
@router.post("/daeun")
async def get_daeun(data: BirthInput):
    """대운(大運) 10년 주기 운세"""
    chart = calculate_full_chart(
        data.birth_year, data.birth_month, data.birth_day,
        data.birth_hour, data.birth_minute, data.gender, data.city
    )
    daeun = calculate_daeun(data.birth_year, data.birth_month, data.birth_day, data.gender, chart)
    chart_summary = _build_chart_summary(chart, data.name)

    # 현재 대운 찾기
    current_age = date.today().year - data.birth_year
    current_daeun = next((d for d in daeun if d["start_age"] <= current_age <= d["end_age"]), daeun[0])

    prompt = (
        f"{chart_summary}\n"
        f"Current Age: {current_age}\n"
        f"Current 10-Year Fortune Cycle (Daeun): {current_daeun['stem']}{current_daeun['branch']} "
        f"(Ages {current_daeun['start_age']}-{current_daeun['end_age']}, "
        f"{ELEMENT_EN.get(current_daeun['element'],'')} element)\n\n"
        f"Provide a reading for the current 10-year fortune cycle. "
        f"Explain what major themes, opportunities, and challenges this period brings. "
        f"Give advice for navigating this cycle successfully in the Cambodian context "
        f"(career growth, family, spiritual practice). Write 3 paragraphs."
    )
    ai_text = _ai_fortune(prompt, max_tokens=800, language=data.language)

    return {
        "success": True,
        "daeun": daeun,
        "current_daeun": current_daeun,
        "current_age": current_age,
        "chart": chart,
        "ai_reading": ai_text,
    }


# ─── 헬스체크 ─────────────────────────────────────────────────────
@router.get("/health")
async def health():
    return {"status": "ok", "version": "2.0", "engine": "sajupy+korean-lunar-calendar"}


# ─── 오늘 날짜 정보 ───────────────────────────────────────────────
@router.get("/today")
async def get_today():
    """오늘 날짜의 일주 및 음력 정보"""
    today = date.today()
    dp = calculate_ilun(today)
    lunar = solar_to_lunar(today.year, today.month, today.day)
    return {
        "success": True,
        "date": today.isoformat(),
        "day_pillar": f"{dp['stem']}{dp['branch']}",
        "day_pillar_detail": dp,
        "lunar": lunar,
    }


# ─── 음력 변환 ───────────────────────────────────────────────────
@router.get("/lunar-convert")
async def lunar_convert(year: int, month: int, day: int):
    """양력 → 음력 변환"""
    lunar = solar_to_lunar(year, month, day)
    return {"success": True, "solar": f"{year}-{month:02d}-{day:02d}", "lunar": lunar}
