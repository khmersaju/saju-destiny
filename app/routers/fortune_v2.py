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
# Persistent Volume 우선 (사용자 DB와 동일한 볼륨에 저장)
_cache_env = os.getenv("CACHE_DB_PATH")
if _cache_env:
    _DB_CACHE_PATH = Path(_cache_env)
elif Path("/data").exists():
    _DB_CACHE_PATH = Path("/data/fortune_cache.db")
else:
    _DB_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "fortune_cache.db"
_DB_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

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
    compat_type: str = Field(default="love", description="love|business|friendship|study|work|family")
    person_a_occupation: Optional[str] = Field(default=None)
    person_a_interests: Optional[str] = Field(default=None)
    person_b_occupation: Optional[str] = Field(default=None)
    person_b_interests: Optional[str] = Field(default=None)


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
# 캐시 버전: v3 (네이티브 언어 직접 생성으로 전환)
_CACHE_VERSION = "v4-rich"

def _make_cache_key(prompt: str, language: str) -> str:
    """입력값 기반 캐시 키 생성 (동일 입력 = 동일 키)"""
    raw = json.dumps({"prompt": prompt, "lang": language, "ver": _CACHE_VERSION}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


# ─── 언어별 시스템 프롬프트 ────────────────────────────────────────────
_SYSTEM_EN = (
    "You are a master Saju (Four Pillars of Destiny) fortune teller "
    "with deep knowledge of Cambodian culture and the Khmer way of life. "
    "You interpret destiny through the ancient principles of the Four Pillars, "
    "Five Elements (Wood, Fire, Earth, Metal, Water), Yin-Yang balance, "
    "and the 60-year Sexagenary cycle. "
    "Your readings are warm, insightful, practical, and culturally respectful. "
    "IMPORTANT: Do NOT reference any specific religion, religious figures, "
    "temples, prayers, or religious practices. "
    "Focus only on natural cosmic principles, elemental balance, and practical life guidance. "
    "Always provide actionable advice relevant to Cambodian daily life. "
    "Write your entire response in clear, natural, flowing English. "
    "Avoid awkward phrasing, overly literal constructions, or translation-like sentence structures. "
    "Every sentence must read as if written by a native English speaker."
)

_SYSTEM_KM = (
    "អ្នកជាគ្រូសាស្ត្រាចារ្យ Saju (Four Pillars of Destiny) ដែលមានចំណេះដឹងស៊ីជម្រៅ "
    "អំពីវប្បធម៌ខ្មែរ និងជីវិតប្រចាំថ្ងៃរបស់ជនជាតិខ្មែរ។ "
    "អ្នកបកស្រាយវាសនាតាមរយៈគោលការណ៍បុរាណនៃ Four Pillars (សសរទាំង ៤), "
    "Five Elements (ធាតុ ៥: ឈើ ភ្លើង ដី លោហ ទឹក), Yin-Yang (យឹន-យាង), "
    "និងវដ្ត ៦០ ឆ្នាំ (Sexagenary cycle)។ "
    "សរសេរជាភាសាខ្មែរដ៏ស្រស់ស្អាត ងាយស្រួលយល់ និងពេញលេញ។ "
    "ចំពោះពាក្យបច្ចេកទេសសាស្ត្រា (Four Pillars, Day Master, Wood, Fire, Earth, Metal, Water, Yin, Yang, "
    "និងឈ្មោះសត្វ ១២ ឆ្នាំ) ត្រូវសរសេរជាភាសាអង់គ្លេស ហើយបន្ថែមន័យខ្មែរក្នុងវង់ក្រចក ឧ. Wood (ឈើ), Rooster (មាន់)។ "
    "ប្រយោគទាំងអស់ក្រៅពីពាក្យបច្ចេកទេស ត្រូវតែជាភាសាខ្មែរ ។ "
    "កុំយោងសាសនា ទីវត្ត ការអធិស្ឋាន ឬការអនុវត្តសាសនា។ "
    "ផ្តោតលើគោលការណ៍ធម្មជាតិ ការតុល្យភាពធាតុ និងការណែនាំជីវិតជាក់ស្តែង។"
)

_SYSTEM_KO = (
    "당신은 사주(四柱) 명리학의 대가입니다. "
    "한국의 전통 사주 명리학과 오행(五行) 이론에 정통하며, 캄보디아 문화와 생활 방식을 깊이 이해합니다. "
    "천간(天干), 지지(地支), 오행(木·火·土·金·水), 음양(陰陽), 육십갑자(六十甲子)의 원리로 운명을 풀이합니다. "
    "\n\n"
    "[언어 규칙 — 반드시 준수]\n"
    "1. 모든 풀이는 자연스러운 한국어로 작성한다. 번역투, 직역체, 어색한 문장은 절대 금지.\n"
    "2. 사주 전문 용어는 한자 병기를 사용한다: 사주(四柱), 오행(五行), 일간(日干), 목(木), 화(火), 토(土), 금(金), 수(水), 음(陰), 양(陽).\n"
    "3. 영어 단어(Wood, Metal, Fire, Earth, Water, Day Master, Four Pillars 등)를 풀이 본문에 절대 사용하지 않는다.\n"
    "4. 띠 이름은 한국어로 표기한다: 쥐띠, 소띠, 호랑이띠, 토끼띠, 용띠, 뱀띠, 말띠, 양띠, 원숭이띠, 닭띠, 개띠, 돼지띠.\n"
    "5. 문장은 간결하고 명확하게 쓴다. 중복 표현, 불필요한 수식어, 번역체 문장 구조를 피한다.\n"
    "6. 종교, 사찰, 기도, 종교 의식은 언급하지 않는다.\n"
    "7. 오행 상생·상극 원리를 바탕으로 구체적이고 실용적인 조언을 제공한다.\n"
    "8. 어조는 따뜻하고 직접적이며 전문적이다. 과도한 칭찬이나 근거 없는 낙관은 피한다."
)


def _ai_fortune(prompt: str, max_tokens: int = 600, language: str = "en") -> str:
    """
    사주 풀이 텍스트 생성 — 언어별 네이티브 직접 생성 방식.
    ① 동일 입력값이면 캐시에서 즉시 반환 (완전 동일한 내용 보장)
    ② 각 언어별 전용 시스템 프롬프트로 처음부터 해당 언어로 직접 생성
       - en: 영어 네이티브 생성
       - km: 크메르어 네이티브 생성 (전문용어만 영어+크메르어 병기)
       - ko: 한국어 네이티브 생성 (사주 전문용어 한자 병기)
    """
    global _FORTUNE_CACHE

    # ① 캐시 확인: 동일 입력이면 즉시 반환
    cache_key = _make_cache_key(prompt, language)
    if cache_key in _FORTUNE_CACHE:
        return _FORTUNE_CACHE[cache_key]
    db_cached = _db_cache_get(cache_key)
    if db_cached:
        _FORTUNE_CACHE[cache_key] = db_cached
        return db_cached

    # 언어별 시스템 프롬프트 선택
    if language == "ko":
        system_prompt = _SYSTEM_KO
        token_multiplier = 1.8  # 한국어는 영어 대비 토큰 약 1.5~2배
    elif language == "km":
        system_prompt = _SYSTEM_KM
        token_multiplier = 3.5  # 크메르어 유니코드는 영어 대비 약 3~3.5배
    else:
        system_prompt = _SYSTEM_EN
        token_multiplier = 1.0

    actual_max_tokens = int(max_tokens * token_multiplier)

    try:
        c = _get_client()
        resp = c.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=actual_max_tokens,
            temperature=0,
            seed=42,
        )
        result_text = resp.choices[0].message.content.strip()

        _FORTUNE_CACHE[cache_key] = result_text
        _db_cache_set(cache_key, language, result_text)
        return result_text

    except Exception as e:
        return f"[Fortune reading temporarily unavailable: {str(e)[:60]}]"


def _get_type_scores(compat: dict, compat_type: str) -> dict:
    """궁합 유형별 세분화 점수 반환 (30~100)"""
    base = compat['score']
    love = compat.get('love_score', base)
    marriage = compat.get('marriage_score', base)
    business = compat.get('business_score', base)
    friendship = compat.get('friendship_score', base)
    # study, work, family 점수 파생
    study = max(30, min(100, base + (5 if compat.get('animal_bonus', 0) >= 0 else -8)))
    work = max(30, min(100, business - 4))
    family = max(30, min(100, base + (8 if compat.get('animal_bonus', 0) > 0 else -4)))

    scores_map = {
        'love': {'main': love, 'sub': {'Romance': love, 'Marriage': marriage, 'Communication': max(30, min(100, base+3)), 'Trust': max(30, min(100, base-2))}},
        'business': {'main': business, 'sub': {'Leadership': max(30, min(100, business+3)), 'Finance': max(30, min(100, business-5)), 'Strategy': max(30, min(100, business+2)), 'Communication': max(30, min(100, base-3))}},
        'friendship': {'main': friendship, 'sub': {'Chemistry': friendship, 'Support': max(30, min(100, friendship+4)), 'Fun': max(30, min(100, friendship+6)), 'Loyalty': max(30, min(100, base-2))}},
        'study': {'main': study, 'sub': {'Focus': study, 'Motivation': max(30, min(100, study+5)), 'Collaboration': max(30, min(100, study-3)), 'Balance': max(30, min(100, base))}},
        'work': {'main': work, 'sub': {'Teamwork': work, 'Productivity': max(30, min(100, work+4)), 'Conflict': max(30, min(100, work-6)), 'Growth': max(30, min(100, work+3))}},
        'family': {'main': family, 'sub': {'Harmony': family, 'Support': max(30, min(100, family+5)), 'Understanding': max(30, min(100, base-3)), 'Bond': max(30, min(100, family+2))}},
    }
    return scores_map.get(compat_type, scores_map['love'])


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


# ─── 언어별 섹션 헤더 번역 헬퍼 ────────────────────────────────────
def _section_headings(lang: str) -> dict:
    """언어별 섹션 헤더 반환 — 프롬프트에 직접 삽입"""
    if lang == "ko":
        return {
            # lifetime
            "personality": "성격과 운명",
            "career_wealth": "직업과 재물",
            "love": "사랑과 인연",
            "health": "건강과 활력",
            "guidance": "인생 조언",
            # yearly
            "year_overview": "올해의 운세",
            "career_finance": "직업과 재정",
            "love_family": "사랑과 가정",
            "health_timing": "건강과 길한 시기",
            # daily
            "today_energy": "오늘의 기운",
            "actions": "행동 지침",
            "lucky": "행운의 요소",
            # compat
            "romantic_chemistry": "연애 궁합",
            "communication": "소통과 이해",
            "marriage_family": "결혼과 가정",
            "financial_harmony": "재정적 조화",
            "love_advice": "연애 조언",
            "leadership": "리더십과 의사결정",
            "wealth_revenue": "재물과 수익",
            "risk_strategy": "위험 감수와 전략",
            "conflict_work": "갈등과 소통",
            "business_advice": "비즈니스 조언",
            "natural_connection": "자연스러운 유대",
            "shared_activities": "공통 관심사",
            "support_hard_times": "어려울 때의 지지",
            "friction": "갈등 요인",
            "friendship_advice": "우정 조언",
            "learning_styles": "학습 스타일",
            "focus_motivation": "집중력과 동기",
            "academic_strengths": "학업 강점",
            "study_conflicts": "학습 갈등",
            "study_advice": "학습 전략 조언",
            "work_style": "업무 스타일",
            "team_dynamics": "팀 역학",
            "stress_responses": "스트레스 반응",
            "career_growth": "커리어 성장",
            "workplace_advice": "직장 조언",
            "family_roles": "가족 역할",
            "emotional_support": "정서적 지지",
            "generational_gaps": "세대 차이",
            "shared_values": "공유 가치관",
            "harmony_advice": "가족 화합 조언",
        }
    elif lang == "km":
        return {
            "personality": "បុគ្គលិកលក្ខណៈ និងវាសនា",
            "career_wealth": "អាជីព និងទ្រព្យសម្បត្តិ",
            "love": "ស្នេហា និងទំនាក់ទំនង",
            "health": "សុខភាព និងថាមពល",
            "guidance": "ការណែនាំជីវិត",
            "year_overview": "ទិដ្ឋភាពទូទៅឆ្នាំ",
            "career_finance": "អាជីព និងហិរញ្ញវត្ថុ",
            "love_family": "ស្នេហា និងគ្រួសារ",
            "health_timing": "សុខភាព និងពេលវេលាល្អ",
            "today_energy": "ថាមពលថ្ងៃនេះ",
            "actions": "សកម្មភាព និងការប្រុងប្រយ័ត្ន",
            "lucky": "ធាតុមង្គល",
            "romantic_chemistry": "គីមីស្នេហា",
            "communication": "ការទំនាក់ទំនង",
            "marriage_family": "អាពាហ៍ពិពាហ៍ និងគ្រួសារ",
            "financial_harmony": "ភាពសុខដុមហិរញ្ញវត្ថុ",
            "love_advice": "ដំបូន្មានស្នេហា",
            "leadership": "ភាពជាអ្នកដឹកនាំ",
            "wealth_revenue": "ទ្រព្យ និងចំណូល",
            "risk_strategy": "យុទ្ធសាស្ត្រ",
            "conflict_work": "ជម្លោះ និងការទំនាក់ទំនង",
            "business_advice": "ដំបូន្មានអាជីវកម្ម",
            "natural_connection": "ទំនាក់ទំនងធម្មជាតិ",
            "shared_activities": "សកម្មភាពរួម",
            "support_hard_times": "ការគាំទ្រពេលលំបាក",
            "friction": "ចំណុចផ្ទុយ",
            "friendship_advice": "ដំបូន្មានមិត្តភាព",
            "learning_styles": "រចនាប័ទ្មរៀន",
            "focus_motivation": "ការផ្តោតអារម្មណ៍",
            "academic_strengths": "ភាពខ្លាំងសិក្សា",
            "study_conflicts": "ជម្លោះការសិក្សា",
            "study_advice": "ដំបូន្មានការសិក្សា",
            "work_style": "រចនាប័ទ្មការងារ",
            "team_dynamics": "ថាមពលក្រុម",
            "stress_responses": "ការឆ្លើយតបស្ត្រេស",
            "career_growth": "ការលូតលាស់អាជីព",
            "workplace_advice": "ដំបូន្មានកន្លែងការងារ",
            "family_roles": "តួនាទីគ្រួសារ",
            "emotional_support": "ការគាំទ្រអារម្មណ៍",
            "generational_gaps": "គម្លាតជំនាន់",
            "shared_values": "តម្លៃរួម",
            "harmony_advice": "ដំបូន្មានភាពសុខដុមគ្រួសារ",
        }
    else:  # en
        return {
            "personality": "Personality & Destiny",
            "career_wealth": "Career & Wealth",
            "love": "Love & Relationships",
            "health": "Health & Vitality",
            "guidance": "Life Guidance",
            "year_overview": "Year Overview",
            "career_finance": "Career & Finance",
            "love_family": "Love & Family",
            "health_timing": "Health & Lucky Timing",
            "today_energy": "Today's Energy",
            "actions": "Best Actions & Cautions",
            "lucky": "Lucky Elements",
            "romantic_chemistry": "Romantic Chemistry",
            "communication": "Communication & Understanding",
            "marriage_family": "Marriage & Family Life",
            "financial_harmony": "Financial Harmony",
            "love_advice": "Love Advice",
            "leadership": "Leadership & Decision-Making",
            "wealth_revenue": "Wealth & Revenue Generation",
            "risk_strategy": "Risk & Strategy Alignment",
            "conflict_work": "Conflict & Communication at Work",
            "business_advice": "Business Advice",
            "natural_connection": "Natural Connection",
            "shared_activities": "Shared Activities & Interests",
            "support_hard_times": "Support in Hard Times",
            "friction": "Friction Points",
            "friendship_advice": "Friendship Advice",
            "learning_styles": "Learning Styles",
            "focus_motivation": "Focus & Motivation Energy",
            "academic_strengths": "Academic Strengths Together",
            "study_conflicts": "Study Conflicts",
            "study_advice": "Study Strategy Advice",
            "work_style": "Work Style Compatibility",
            "team_dynamics": "Team Dynamics & Task Division",
            "stress_responses": "Stress & Pressure Responses",
            "career_growth": "Career Growth Together",
            "workplace_advice": "Workplace Advice",
            "family_roles": "Family Roles & Dynamics",
            "emotional_support": "Emotional Support Patterns",
            "generational_gaps": "Generational & Personality Gaps",
            "shared_values": "Shared Values & Traditions",
            "harmony_advice": "Family Harmony Advice",
        }


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
    h = _section_headings(data.language)
    lang_note = (
        "Write the entire reading in natural, fluent Korean (\ud55c\uad6d\uc5b4). Use Saju technical terms with Chinese characters: \uc0ac\uc8fc(\u56db\u67f1), \uc624\ud589(\u4e94\ud589), \uc77c\uac04(\u65e5\u5e72), \ubaa9(\u6728), \ud654(\u706b), \ud1a0(\u571f), \uae08(\u91d1), \uc218(\u6c34). Do NOT use English words in the reading body."
        if data.language == "ko" else
        "Write the entire reading in natural Khmer (\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a). Keep technical terms (Four Pillars, Day Master, element names, zodiac animals) in English with Khmer meaning in parentheses."
        if data.language == "km" else
        "Write the entire reading in clear, natural English. Every sentence must flow naturally \u2014 no translation-like phrasing."
    )
    prompt = (
        f"{chart_summary}\n"
        f"Life Stages (use these scores to calibrate the depth of each life period):\n"
        f"  Early Life (0-30): {life_stages['early_life']['quality']} ({ELEMENT_EN.get(life_stages['early_life']['element'],'')} element, score {life_stages['early_life']['score']}/100)\n"
        f"  Mid Life (31-60): {life_stages['mid_life']['quality']} ({ELEMENT_EN.get(life_stages['mid_life']['element'],'')} element, score {life_stages['mid_life']['score']}/100)\n"
        f"  Late Life (61+): {life_stages['late_life']['quality']} ({ELEMENT_EN.get(life_stages['late_life']['element'],'')} element, score {life_stages['late_life']['score']}/100)\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus}\n\n"
        f"LANGUAGE: {lang_note}\n\n"
        f"Provide a RICH, DETAILED lifetime fortune reading UNIQUE to this person's exact Four Pillars combination.\n"
        f"This reading must feel like a personal consultation from a master fortune teller — not a generic horoscope.\n\n"
        f"IMPORTANT FORMAT RULES:\n"
        f"- Structure into exactly 5 sections, each starting with a ## heading\n"
        f"- Each section: 4-6 sentences — substantive, specific, insightful, no filler\n"
        f"- Use these exact section headings:\n"
        f"  ## {h['personality']}\n"
        f"  ## {h['career_wealth']}\n"
        f"  ## {h['love']}\n"
        f"  ## {h['health']}\n"
        f"  ## {h['guidance']}\n\n"
        f"DEPTH REQUIREMENTS per section:\n"
        f"  {h['personality']}: Describe the core character shaped by their Day Master and dominant element. Explain how their zodiac animal reinforces or contradicts this. Mention how their Yin/Yang polarity affects their approach to life. Describe early life (0-30) tendencies based on the Early Life score.\n"
        f"  {h['career_wealth']}: Name specific career fields that suit their elemental combination. Explain the wealth-building pattern across three life stages using the scores above. Identify the peak earning period and the biggest financial risk period. Give one concrete strategy to maximize their wealth potential.\n"
        f"  {h['love']}: Describe their love personality based on Day Master and gender. Explain what type of partner complements their weak element. Identify the best marriage timing based on elemental cycles. Be honest if their chart shows relationship challenges — and explain how to overcome them.\n"
        f"  {h['health']}: Identify the body systems most vulnerable based on their weak element. Explain how their dominant element can create health excesses if unchecked. Give specific lifestyle recommendations (diet, exercise, rest) aligned with their elemental balance.\n"
        f"  {h['guidance']}: Synthesize the three life stages into a life narrative arc. Give 3 specific, actionable life principles this person should follow based on their chart. End with a motivating statement about their unique destiny potential.\n\n"
        f"Be honest — not all aspects are positive. If weak elements create challenges, name them specifically.\n"
        f"Every insight must be traceable to their actual chart data — no generic statements."
    )
    ai_text = _ai_fortune(prompt, max_tokens=2500, language=data.language)

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

    h = _section_headings(data.language)
    lang_note_yr = (
        "Write the entire reading in natural, fluent Korean (\ud55c\uad6d\uc5b4). Use Saju technical terms with Chinese characters. Do NOT use English words in the reading body."
        if data.language == "ko" else
        "Write the entire reading in natural Khmer (\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a). Keep technical terms in English with Khmer meaning in parentheses."
        if data.language == "km" else
        "Write in clear, natural English. No translation-like phrasing."
    )
    # 세운과 일간의 오행 관계 분석
    elem_interaction_yr = (
        f"The {year} year's {ELEMENT_EN.get(seun['element'],'')} energy "
        f"{'supports and strengthens' if seun['element'] == chart['day_master']['element'] else 'challenges and pressures'} "
        f"their {ELEMENT_EN.get(chart['day_master']['element'],'')} Day Master."
    )
    prompt = (
        f"{chart_summary}\n"
        f"Year {year} Fortune:\n"
        f"  Year Pillar: {seun['stem']}{seun['branch']} ({seun['animal']} year, {ELEMENT_EN.get(seun['element'],'')} element)\n"
        f"  Elemental Interaction: {elem_interaction_yr}\n"
        f"  Dominant personal element: {ELEMENT_EN.get(chart.get('dominant_element',''),'')} | Weak element: {ELEMENT_EN.get(chart.get('weak_element',''),'')}\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_yr}\n\n"
        f"LANGUAGE: {lang_note_yr}\n\n"
        f"Provide a RICH, DETAILED {year} yearly fortune reading UNIQUE to this person's chart.\n"
        f"This must feel like a personalized annual consultation — not a generic yearly horoscope.\n\n"
        f"IMPORTANT FORMAT RULES:\n"
        f"- Structure into exactly 4 sections, each starting with a ## heading\n"
        f"- Each section: 4-6 sentences — substantive, specific, insightful\n"
        f"- Use these exact section headings:\n"
        f"  ## {h['year_overview']}\n"
        f"  ## {h['career_finance']}\n"
        f"  ## {h['love_family']}\n"
        f"  ## {h['health_timing']}\n\n"
        f"DEPTH REQUIREMENTS per section:\n"
        f"  {h['year_overview']}: Explain how the {seun['animal']} year's {ELEMENT_EN.get(seun['element'],'')} energy specifically interacts with this person's chart. Describe the overall tone of the year (expansive, challenging, transitional, etc.). Name the single biggest opportunity and the single biggest risk this year. Describe how their zodiac animal interacts with the year's animal.\n"
        f"  {h['career_finance']}: Identify the 2-3 best months for career moves or financial decisions in {year}. Explain which specific career actions will be rewarded by the year's elemental energy. Warn about the 1-2 months when financial caution is critical. Give a concrete financial strategy for this year based on their chart.\n"
        f"  {h['love_family']}: Describe how the year's energy affects their romantic life or marriage. Identify the best months for relationship milestones (meeting someone, engagement, reconciliation). Explain family dynamics this year — are there tensions or harmony periods? Give specific advice for their relationship situation based on their Day Master.\n"
        f"  {h['health_timing']}: Identify which months carry higher health risk based on elemental clashes. Explain which body systems need attention this year based on their weak element. Give 2 specific health habits to adopt in {year}. Name the luckiest months of the year for overall vitality.\n\n"
        f"Be specific: name actual months (January, March, etc.). Be honest — if the year brings hardship, describe it clearly with constructive guidance."
    )
    ai_text = _ai_fortune(prompt, max_tokens=2000, language=data.language)

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

    lang_note_mo = (
        "Write the entire reading in natural, fluent Korean (\ud55c\uad6d\uc5b4). Use Saju technical terms with Chinese characters. Do NOT use English words in the reading body. Use Korean month names (1\uc6d4, 2\uc6d4 \ub4f1)."
        if data.language == "ko" else
        "Write the entire reading in natural Khmer (\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a). Keep technical terms in English with Khmer meaning in parentheses."
        if data.language == "km" else
        "Write in clear, natural English."
    )
    prompt = (
        f"{chart_summary}\n"
        f"Monthly Fortune for {year} (upcoming 3 months):\n{months_text}\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_mo}\n\n"
        f"LANGUAGE: {lang_note_mo}\n\n"
        f"Provide a RICH, DETAILED monthly fortune reading UNIQUE to this person's chart for each of these 3 months.\n"
        f"Each month must feel like a personalized monthly consultation — not a generic forecast.\n\n"
        f"IMPORTANT FORMAT RULES:\n"
        f"- Use ## [Month Name] as the heading for each month\n"
        f"- Under each month, write 4 substantive paragraphs (not bullet points):\n"
        f"  Paragraph 1 (Overall Energy): Explain how this month's elemental energy interacts with their Day Master and dominant element. Describe the general mood and energy level of the month.\n"
        f"  Paragraph 2 (Career & Finance): Give specific career and financial guidance for this month. Name the best week for action and the week requiring caution. Reference their actual elemental strengths.\n"
        f"  Paragraph 3 (Love & Relationships): Describe the romantic and social energy of the month. Give specific relationship advice based on their Day Master and gender.\n"
        f"  Paragraph 4 (Health & Action): Identify health vulnerabilities this month based on elemental interaction. Give 2 concrete action tips for this specific month.\n"
        f"- Be honest: if a month scores below 55, describe the challenges clearly and give constructive guidance.\n"
        f"- Each month's reading must be clearly different from the others — no repetitive phrasing."
    )
    ai_text = _ai_fortune(prompt, max_tokens=1800, language=data.language)

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

    h = _section_headings(data.language)
    lang_note_day = (
        "Write the entire reading in natural, fluent Korean (\ud55c\uad6d\uc5b4). Use Saju technical terms with Chinese characters. Do NOT use English words in the reading body."
        if data.language == "ko" else
        "Write the entire reading in natural Khmer (\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a). Keep technical terms in English with Khmer meaning in parentheses."
        if data.language == "km" else
        "Write in clear, natural English."
    )
    prompt = (
        f"{chart_summary}\n"
        f"Today's Date: {target.strftime('%B %d, %Y')}\n"
        f"Today's Day Pillar: {ilun['stem']}{ilun['branch']} ({ELEMENT_EN.get(ilun['element'],'')} element, {ilun['branch_en']} day)\n"
        f"Lunar Date: {ilun['lunar']['lunar_iso']}\n"
        f"Dominant personal element: {ELEMENT_EN.get(chart.get('dominant_element',''),'')} | Weak element: {ELEMENT_EN.get(chart.get('weak_element',''),'')}"
        f"\n\n"
        f"GENDER-SPECIFIC GUIDANCE: {gender_focus_day}\n\n"
        f"LANGUAGE: {lang_note_day}\n\n"
        f"Provide a DETAILED daily fortune reading UNIQUE to this person's chart for today.\n"
        f"This must feel like a personalized daily briefing from a master fortune teller.\n\n"
        f"IMPORTANT FORMAT RULES:\n"
        f"- Structure into exactly 3 sections, each starting with a ## heading\n"
        f"- Each section: 3-4 sentences — specific, actionable, insightful\n"
        f"- Use these exact section headings:\n"
        f"  ## {h['today_energy']}\n"
        f"  ## {h['actions']}\n"
        f"  ## {h['lucky']}\n\n"
        f"DEPTH REQUIREMENTS per section:\n"
        f"  {h['today_energy']}: Explain precisely how today's {ELEMENT_EN.get(ilun['element'],'')} energy interacts with their {ELEMENT_EN.get(chart['day_master']['element'],'')} Day Master. Describe whether this creates harmony, tension, or neutrality. Explain how this affects their mental state and energy level today. Reference their zodiac animal's relationship with today's branch ({ilun['branch_en']}).\n"
        f"  {h['actions']}: Give 2 specific things to DO today that align with the elemental energy. Give 2 specific things to AVOID today. Make these practical and relevant to their gender and life context — not generic advice.\n"
        f"  {h['lucky']}: State their lucky color(s) today and why (elemental reasoning). Give their lucky direction and best time window today. End with one personalized motivational insight based on their Day Master and today's energy."
    )
    ai_text = _ai_fortune(prompt, max_tokens=1200, language=data.language)

    # 레이더 차트용 5가지 운세 점수 계산 (30~100, 오행 상생상극 기반)
    from app.services.saju_engine_v2 import _element_score
    day_elem = chart["day_master"]["element"]
    today_elem = ilun["element"]
    dominant = max(chart["five_elements"], key=chart["five_elements"].get)
    import hashlib, json as _json
    seed_str = f"{data.birth_year}{data.birth_month}{data.birth_day}{target.isoformat()}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % 1000
    def _radar_score(base_offset: int) -> int:
        raw = _element_score(today_elem, day_elem, dominant)
        varied = max(30, min(100, raw + base_offset + (seed % 21) - 10))
        return varied
    daily_scores = {
        "wealth":  _radar_score(0),
        "love":    _radar_score(-5),
        "health":  _radar_score(3),
        "career":  _radar_score(-8),
        "study":   _radar_score(5),
    }

    return {
        "success": True,
        "date": target.isoformat(),
        "day_pillar": ilun,
        "chart": chart,
        "ai_reading": ai_text,
        "lucky_color": chart["lucky"]["colors"],
        "lucky_direction": chart["lucky"]["direction"],
        "lucky_numbers": chart["lucky"]["numbers"],
        "daily_scores": daily_scores,
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

    # 궁합 유형별 점수 세분화
    compat_type = getattr(data, 'compat_type', 'love')
    type_scores = _get_type_scores(compat, compat_type)

    # 직업/관심사 컨텍스트
    occ_a = getattr(data, 'person_a_occupation', None) or ''
    int_a = getattr(data, 'person_a_interests', None) or ''
    occ_b = getattr(data, 'person_b_occupation', None) or ''
    int_b = getattr(data, 'person_b_interests', None) or ''
    occ_ctx = ''
    if occ_a or occ_b:
        occ_ctx = f"\nOccupation context: {data.person_a.name} is {occ_a or 'unknown occupation'}, {data.person_b.name} is {occ_b or 'unknown occupation'}."
    if int_a or int_b:
        occ_ctx += f"\nInterests: {data.person_a.name} interests: {int_a or 'not specified'}; {data.person_b.name} interests: {int_b or 'not specified'}."

    # 유형별 프롬프트 (섹션 헤더 구조화 + 테마별 차별화)
    h = _section_headings(data.language)
    lang_note_compat = (
        "Write the entire reading in natural, fluent Korean (\ud55c\uad6d\uc5b4). Use Saju technical terms with Chinese characters: \uc0ac\uc8fc(\u56db\u67f1), \uc624\ud589(\u4e94\ud589), \uc77c\uac04(\u65e5\u5e72), \ubaa9(\u6728), \ud654(\u706b), \ud1a0(\u571f), \uae08(\u91d1), \uc218(\u6c34). Do NOT use English words in the reading body."
        if data.language == "ko" else
        "Write the entire reading in natural Khmer (\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a). Keep technical terms in English with Khmer meaning in parentheses."
        if data.language == "km" else
        "Write in clear, natural English."
    )
    def _compat_header(type_name: str) -> str:
        return (
            f"Person A ({data.person_a.gender.upper()}, {data.person_a.name or 'Person A'}):\n{summary_a}\n"
            f"Person B ({data.person_b.gender.upper()}, {data.person_b.name or 'Person B'}):\n{summary_b}\n"
            f"Compatibility Score: {type_scores['main']}/100\n"
            f"Elemental Interaction: {elem_interaction}{occ_ctx}\n\n"
            f"LANGUAGE: {lang_note_compat}\n\n"
            f"IMPORTANT FORMAT RULES:\n"
            f"- Structure into exactly 5 sections, each starting with a ## heading\n"
            f"- Each section: 4-6 sentences — rich, specific, insightful, no filler\n"
            f"- Every section MUST reference their actual elements ({elem_a} vs {elem_b}) and zodiac animals\n"
            f"- Be honest: if compatibility is low in a specific area, describe the challenge clearly and give 2-3 concrete actionable steps\n"
            f"- If compatibility is high, explain WHY specifically and give 2-3 tips to maximize the synergy\n"
            f"- Do NOT repeat the same advice across sections — each section must offer unique insights\n"
            f"- This reading must feel like a personalized compatibility consultation, not a generic horoscope\n\n"
        )

    type_prompts = {
        'love': (
            f"This is a LOVE & MARRIAGE compatibility reading.\n"
            + _compat_header('love') +
            f"Use these exact section headings:\n"
            f"## {h['romantic_chemistry']}\n"
            f"(How their {elem_a} and {elem_b} elements create or block romantic spark. Name the specific attraction or tension.)\n\n"
            f"## {h['communication']}\n"
            f"(How they express love differently based on their Day Masters. Where misunderstandings arise and how to bridge them.)\n\n"
            f"## {h['marriage_family']}\n"
            f"(Long-term compatibility: who takes which role, children timing based on elements, home harmony.)\n\n"
            f"## {h['financial_harmony']}\n"
            f"(How their elemental energies align or clash around money, spending habits, and shared financial goals.)\n\n"
            f"## {h['love_advice']}\n"
            f"(If score below 65: 3 specific actions to overcome elemental clashes. If above 65: 3 tips to deepen the bond. Be direct.)"
        ),
        'business': (
            f"This is a BUSINESS PARTNERSHIP compatibility reading.\n"
            + _compat_header('business') +
            f"Use these exact section headings:\n"
            f"## {h['leadership']}\n"
            f"(Who naturally leads vs. supports based on their {elem_a}/{elem_b} elements. How they make decisions together.)\n\n"
            f"## {h['wealth_revenue']}\n"
            f"(Their combined elemental energy for attracting money. Which business sectors suit their combined chart.)\n\n"
            f"## {h['risk_strategy']}\n"
            f"(Do they take risks similarly or clash? How their zodiac animals affect business strategy and timing.)\n\n"
            f"## {h['conflict_work']}\n"
            f"(Specific professional friction points from their elemental clash. How to resolve business disagreements.)\n\n"
            f"## {h['business_advice']}\n"
            f"(If score below 65: 3 concrete risk mitigation strategies for this partnership. If above 65: 3 ways to maximize their combined business power. Reference specific industries or roles.)"
        ),
        'friendship': (
            f"This is a FRIENDSHIP compatibility reading.\n"
            + _compat_header('friendship') +
            f"Use these exact section headings:\n"
            f"## {h['natural_connection']}\n"
            f"(The immediate vibe between their {elem_a} and {elem_b} elements. Do they click instantly or need time to warm up?)\n\n"
            f"## {h['shared_activities']}\n"
            f"(Based on their dominant elements, what activities, hobbies, or social settings they genuinely enjoy together.)\n\n"
            f"## {h['support_hard_times']}\n"
            f"(How each person shows up for the other during stress. Who gives emotional support vs. practical help based on their elements.)\n\n"
            f"## {h['friction']}\n"
            f"(Specific personality clashes from their elemental interaction. What topics or situations cause tension between them.)\n\n"
            f"## {h['friendship_advice']}\n"
            f"(If score below 60: honest assessment of whether this friendship can thrive and what specific effort is needed. If above 60: 3 ways to deepen this bond.)"
        ),
        'study': (
            f"This is a STUDY PARTNER compatibility reading.\n"
            + _compat_header('study') +
            f"Use these exact section headings:\n"
            f"## {h['learning_styles']}\n"
            f"(How their {elem_a} and {elem_b} elements shape how each person learns: visual vs. analytical, fast vs. methodical, etc.)\n\n"
            f"## {h['focus_motivation']}\n"
            f"(Does studying together energize or drain them? Which element dominates the study dynamic and how it affects concentration.)\n\n"
            f"## {h['academic_strengths']}\n"
            f"(What each person uniquely contributes to collaborative study: one may excel at memorization, the other at problem-solving.)\n\n"
            f"## {h['study_conflicts']}\n"
            f"(Specific incompatibilities: pace differences, subject preferences, or distraction patterns from their elemental clash.)\n\n"
            f"## {h['study_advice']}\n"
            f"(If score below 60: honest advice on whether to study together or separately, and how to compensate. If above 60: specific study methods that leverage their elemental synergy.)"
        ),
        'work': (
            f"This is a WORK COLLEAGUE compatibility reading.\n"
            + _compat_header('work') +
            f"Use these exact section headings:\n"
            f"## {h['work_style']}\n"
            f"(How their {elem_a} and {elem_b} elements shape their professional approach: one may be detail-oriented, the other big-picture.)\n\n"
            f"## {h['team_dynamics']}\n"
            f"(Natural role division based on their elements: who leads projects, who executes, who mediates. Specific task types each excels at.)\n\n"
            f"## {h['stress_responses']}\n"
            f"(How each person reacts under deadline pressure based on their Day Master. Do their stress responses complement or clash?)\n\n"
            f"## {h['career_growth']}\n"
            f"(Can they help each other advance? Which career paths or industries benefit from their combined elemental energy.)\n\n"
            f"## {h['workplace_advice']}\n"
            f"(If score below 60: 3 specific strategies to prevent professional conflicts and maintain productivity. If above 60: 3 ways to leverage their elemental synergy for career advancement.)"
        ),
        'family': (
            f"This is a FAMILY BOND compatibility reading.\n"
            + _compat_header('family') +
            f"Use these exact section headings:\n"
            f"## {h['family_roles']}\n"
            f"(How their {elem_a} and {elem_b} elements define natural family roles: who nurtures, who disciplines, who mediates.)\n\n"
            f"## {h['emotional_support']}\n"
            f"(How each person expresses care and support within the family. Where emotional mismatches occur based on their Day Masters.)\n\n"
            f"## {h['generational_gaps']}\n"
            f"(Specific personality differences explained by their elemental clash. How age or life stage differences affect their bond.)\n\n"
            f"## {h['shared_values']}\n"
            f"(How their combined elements align with family values: respect for elders, shared responsibilities, financial support.)\n\n"
            f"## {h['harmony_advice']}\n"
            f"(If score below 60: specific actions to heal elemental conflicts and restore harmony. If above 60: 3 ways to strengthen and celebrate this family bond.)"
        ),
    }
    prompt = type_prompts.get(compat_type, type_prompts['love'])
    ai_text = _ai_fortune(prompt, max_tokens=2500, language=data.language)

    return {
        "success": True,
        "compatibility": compat,
        "compat_type": compat_type,
        "type_scores": type_scores,
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

# ─── 사주 공유 카드 이미지 생성 ───────────────────────────────────
from fastapi.responses import Response as FastAPIResponse

@router.post("/share-card")
async def generate_share_card_api(data: BirthInput):
    """
    사주 차트 SNS 공유 카드 이미지 생성 (1080x1350 PNG)
    Facebook, Instagram, Telegram 공유 최적화
    """
    try:
        from app.services.share_card import generate_share_card

        chart = calculate_full_chart(
            data.birth_year, data.birth_month, data.birth_day,
            data.birth_hour, data.birth_minute,
            data.gender, data.city or "Phnom Penh"
        )

        gender_label = "Male" if data.gender == "male" else "Female"
        birth_info = f"{data.birth_year}.{data.birth_month}.{data.birth_day}  |  {gender_label}"

        img_bytes = generate_share_card(
            name=data.name or "Anonymous",
            birth_info=birth_info,
            pillars=chart["pillars"],
            five_elements=chart["five_elements"],
            day_master=chart["day_master"],
            animal_sign=chart.get("animal_sign", ""),
            animal_sign_km=chart.get("animal_sign_km", ""),
            dominant_element=chart.get("dominant_element", "목"),
            app_url="https://web-production-d0bd4.up.railway.app",
            lang=getattr(data, "language", "en"),
        )

        return FastAPIResponse(
            content=img_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": "inline; filename=saju-destiny-card.png",
                "Cache-Control": "public, max-age=3600",
            }
        )
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=str(e))
