"""
AI Khmer Destiny - Fortune API Router
사주 운세 API 엔드포인트 정의
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.models import (
    BirthInfo, FortuneResponse, PremiumReportResponse,
    DailyFortuneResponse, MonthlyFortuneResponse,
)
from app.models.saju_models import DailyFortune, MonthlyFortune
from app.services.saju_engine import calculate_saju_chart, build_free_summary, get_today_fortune
from app.services.ai_report import generate_premium_report, generate_daily_fortune

router = APIRouter()


@router.post(
    "/basic",
    response_model=FortuneResponse,
    summary="무료 기본 사주 운세",
    description="생년월일시를 입력받아 만세력 계산 및 무료 기본 운세를 반환합니다.",
)
def create_basic_fortune(info: BirthInfo):
    """무료 기본 운세 — 사주 차트 + 요약 리포트"""
    try:
        chart = calculate_saju_chart(info)
        summary, advice = build_free_summary(info, chart)
        today_fortune = get_today_fortune(chart)
        
        return FortuneResponse(
            profile=info,
            chart=chart,
            free_summary=summary,
            free_advice=advice,
            today_fortune=today_fortune,
            disclaimer=(
                "This result is for entertainment and self-reflection only. "
                "Korean Saju analysis is based on traditional Four Pillars of Destiny principles. "
                "For major life decisions, consult qualified professionals."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Saju calculation error: {str(e)}")


@router.post(
    "/premium",
    response_model=PremiumReportResponse,
    summary="프리미엄 AI 사주 리포트",
    description="AI(GPT)를 활용한 상세한 개인 맞춤형 사주 리포트를 생성합니다.",
)
def create_premium_report(info: BirthInfo):
    """프리미엄 AI 리포트 — 심층 분석 + 월별 운세"""
    try:
        chart = calculate_saju_chart(info)
        report, source = generate_premium_report(info, chart)
        
        return PremiumReportResponse(
            profile=info,
            chart=chart,
            report=report,
            source=source,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Premium report generation error: {str(e)}")


@router.post(
    "/daily",
    summary="일별 운세",
    description="특정 날짜의 일별 운세를 생성합니다.",
)
def create_daily_fortune(
    info: BirthInfo,
    target_date: Optional[str] = Query(None, description="날짜 (YYYY-MM-DD), 기본값: 오늘"),
):
    """일별 운세 생성"""
    try:
        chart = calculate_saju_chart(info)
        daily_data = generate_daily_fortune(info, chart, target_date)
        
        daily = DailyFortune(
            date=daily_data.get("date", ""),
            overall=daily_data.get("overall", ""),
            love=daily_data.get("love", ""),
            career=daily_data.get("career", ""),
            money=daily_data.get("money", ""),
            health=daily_data.get("health", ""),
            lucky_color=daily_data.get("lucky_color", chart.lucky_color),
            lucky_number=daily_data.get("lucky_number", chart.lucky_number),
        )
        
        return DailyFortuneResponse(
            profile=info,
            chart=chart,
            daily=daily,
            source="ai_generated" if "ai" not in daily_data.get("source", "") else "rule_based",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Daily fortune error: {str(e)}")


@router.get(
    "/elements",
    summary="오행 정보 조회",
    description="오행(목화토금수)의 특성 및 의미 정보를 반환합니다.",
)
def get_elements_info():
    """오행 기본 정보 반환"""
    return {
        "five_elements": {
            "목 (Wood / ឈើ)": {
                "korean": "목(木)",
                "khmer": "ឈើ",
                "english": "Wood",
                "color": "Green",
                "direction": "East",
                "season": "Spring",
                "qualities": "Growth, creativity, flexibility, ambition",
                "lucky_number": 3,
            },
            "화 (Fire / ភ្លើង)": {
                "korean": "화(火)",
                "khmer": "ភ្លើង",
                "english": "Fire",
                "color": "Red",
                "direction": "South",
                "season": "Summer",
                "qualities": "Passion, charisma, transformation, energy",
                "lucky_number": 9,
            },
            "토 (Earth / ដី)": {
                "korean": "토(土)",
                "khmer": "ដី",
                "english": "Earth",
                "color": "Yellow",
                "direction": "Center",
                "season": "All seasons",
                "qualities": "Stability, reliability, nurturing, harmony",
                "lucky_number": 5,
            },
            "금 (Metal / លោហៈ)": {
                "korean": "금(金)",
                "khmer": "លោហៈ",
                "english": "Metal",
                "color": "White",
                "direction": "West",
                "season": "Autumn",
                "qualities": "Precision, discipline, justice, strength",
                "lucky_number": 4,
            },
            "수 (Water / ទឹក)": {
                "korean": "수(水)",
                "khmer": "ទឹក",
                "english": "Water",
                "color": "Black/Blue",
                "direction": "North",
                "season": "Winter",
                "qualities": "Intuition, wisdom, adaptability, depth",
                "lucky_number": 1,
            },
        },
        "note": "Five Elements (오행/Wu Xing) form the foundation of Korean Saju analysis.",
    }
