"""
AI Khmer Destiny - Pydantic Data Models
캄보디아 한국식 사주명리학 AI 운세 앱 데이터 모델
"""
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class FocusArea(str, Enum):
    general = "general"
    love = "love"
    marriage = "marriage"
    career = "career"
    business = "business"
    money = "money"
    study_abroad = "study_abroad"
    lucky_date = "lucky_date"


class BirthInfo(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="이름 (Name)")
    gender: Gender
    birth_year: int = Field(..., ge=1900, le=2100, description="출생 연도")
    birth_month: int = Field(..., ge=1, le=12, description="출생 월")
    birth_day: int = Field(..., ge=1, le=31, description="출생 일")
    birth_hour: Optional[int] = Field(None, ge=0, le=23, description="출생 시 (0-23), 모르면 null")
    birth_minute: Optional[int] = Field(0, ge=0, le=59, description="출생 분 (0-59)")
    country: str = Field("Cambodia", description="출생 국가")
    city: str = Field("Phnom Penh", description="출생 도시")
    longitude: Optional[float] = Field(None, description="경도 (태양시 보정용, 프놈펜=104.9282)")
    utc_offset: float = Field(7.0, description="UTC 오프셋 (캄보디아=7)")
    focus_area: FocusArea = Field(FocusArea.general, description="관심 분야")
    language: str = Field("en", description="응답 언어: en/km/ko")


class Pillar(BaseModel):
    """사주 기둥 (년주/월주/일주/시주)"""
    stem: str = Field(..., description="천간 (한자)")
    branch: str = Field(..., description="지지 (한자)")
    stem_korean: str = Field(..., description="천간 (한국어)")
    branch_korean: str = Field(..., description="지지 (한국어/동물)")
    element: str = Field(..., description="오행 (목/화/토/금/수)")
    yin_yang: str = Field(..., description="음양")
    pillar_name: str = Field(..., description="기둥 이름 (년주/월주/일주/시주)")


class SajuChart(BaseModel):
    """사주팔자 차트 전체"""
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    hour_pillar: Optional[Pillar] = None
    five_elements: Dict[str, int] = Field(..., description="오행 분포 {목:n, 화:n, 토:n, 금:n, 수:n}")
    dominant_element: str = Field(..., description="주도 오행")
    weak_element: str = Field(..., description="약한 오행")
    day_stem_element: str = Field(..., description="일간 오행 (자신의 오행)")
    day_stem_yin_yang: str = Field(..., description="일간 음양")
    lucky_color: str = Field(..., description="행운의 색상")
    lucky_direction: str = Field(..., description="행운의 방향")
    lucky_number: int = Field(..., description="행운의 숫자")
    animal_sign: str = Field(..., description="띠 (동물)")
    calculation_note: str = Field(..., description="계산 참고사항")


class FortuneResponse(BaseModel):
    """무료 기본 운세 응답"""
    profile: BirthInfo
    chart: SajuChart
    free_summary: str = Field(..., description="무료 요약 운세")
    free_advice: List[str] = Field(..., description="무료 조언 목록")
    today_fortune: str = Field(..., description="오늘의 운세")
    disclaimer: str = Field(..., description="면책 조항")


class DailyFortune(BaseModel):
    """일별 운세"""
    date: str
    overall: str
    love: str
    career: str
    money: str
    health: str
    lucky_color: str
    lucky_number: int


class MonthlyFortune(BaseModel):
    """월별 운세"""
    year_month: str
    overall: str
    key_events: List[str]
    advice: str
    lucky_period: str


class PremiumReport(BaseModel):
    """프리미엄 AI 리포트"""
    title: str
    personality: str = Field(..., description="성격 및 기질 분석")
    strengths: str = Field(..., description="강점")
    weaknesses: str = Field(..., description="약점 및 주의사항")
    love: str = Field(..., description="연애/결혼운")
    career: str = Field(..., description="직업/사업운")
    money: str = Field(..., description="재물운")
    study_abroad: str = Field(..., description="유학/해외운 (한국 포함)")
    lucky_items: str = Field(..., description="행운 아이템 및 색상")
    action_advice_30_days: List[str] = Field(..., min_length=3, max_length=6, description="30일 행동 지침")
    monthly_fortune: List[MonthlyFortune] = Field(default=[], description="월별 운세 (3개월)")
    cambodia_cultural_note: str = Field(..., description="캄보디아 문화 맞춤 조언")
    premium_disclaimer: str = Field(..., description="프리미엄 면책 조항")


class PremiumReportResponse(BaseModel):
    """프리미엄 리포트 전체 응답"""
    profile: BirthInfo
    chart: SajuChart
    report: PremiumReport
    source: str = Field(..., description="생성 소스 (openai/fallback)")


class DailyFortuneResponse(BaseModel):
    """일별 운세 응답"""
    profile: BirthInfo
    chart: SajuChart
    daily: DailyFortune
    source: str


class MonthlyFortuneResponse(BaseModel):
    """월별 운세 응답"""
    profile: BirthInfo
    chart: SajuChart
    monthly: MonthlyFortune
    source: str
