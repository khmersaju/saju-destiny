"""
Saju Destiny - 프리미엄 리포트 생성 서비스
OpenAI GPT를 활용한 캄보디아 맞춤형 사주 풀이 생성
"""
import json
import os
from typing import Tuple
from datetime import date

from app.models import BirthInfo, SajuChart, PremiumReport
from app.models.saju_models import MonthlyFortune


# ─── JSON 스키마 정의 ────────────────────────────────────────────────────────────
PREMIUM_REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "personality": {"type": "string"},
        "strengths": {"type": "string"},
        "weaknesses": {"type": "string"},
        "love": {"type": "string"},
        "career": {"type": "string"},
        "money": {"type": "string"},
        "study_abroad": {"type": "string"},
        "lucky_items": {"type": "string"},
        "action_advice_30_days": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 6,
        },
        "monthly_fortune": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "year_month": {"type": "string"},
                    "overall": {"type": "string"},
                    "key_events": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 4,
                    },
                    "advice": {"type": "string"},
                    "lucky_period": {"type": "string"},
                },
                "required": ["year_month", "overall", "key_events", "advice", "lucky_period"],
            },
            "minItems": 3,
            "maxItems": 3,
        },
        "cambodia_cultural_note": {"type": "string"},
        "premium_disclaimer": {"type": "string"},
    },
    "required": [
        "title", "personality", "strengths", "weaknesses",
        "love", "career", "money", "study_abroad",
        "lucky_items", "action_advice_30_days", "monthly_fortune",
        "cambodia_cultural_note", "premium_disclaimer",
    ],
}


def _build_system_prompt() -> str:
    return """You are an expert fortune analyst specializing in Saju (Four Pillars of Destiny) 
for Cambodian users. Your role is to:

1. Provide warm, practical, and culturally sensitive fortune readings
2. Blend Saju wisdom with Cambodian cultural values (family, harmony, prosperity)
3. Write in clear, accessible English (the app will translate to Khmer)
4. Never make deterministic predictions — use language like "tends to", "may", "has potential for"
5. Focus on empowerment and positive guidance, not fatalism
6. Include practical, actionable advice relevant to Cambodian life contexts
7. Respect Buddhist values common in Cambodia (karma, mindfulness, merit-making)
8. NEVER provide medical, legal, financial investment, or immigration guarantees
9. Keep each section concise but meaningful (2-4 sentences per section)"""


def _build_user_prompt(info: BirthInfo, chart: SajuChart) -> str:
    today = date.today()
    months = []
    for i in range(3):
        m = today.month + i
        y = today.year
        if m > 12:
            m -= 12
            y += 1
        months.append(f"{y}-{m:02d}")
    
    profile_data = {
        "name": info.name,
        "gender": info.gender,
        "birth_date": f"{info.birth_year}-{info.birth_month:02d}-{info.birth_day:02d}",
        "birth_hour": info.birth_hour,
        "city": info.city,
        "country": info.country,
        "focus_area": info.focus_area,
    }
    
    chart_data = {
        "year_pillar": f"{chart.year_pillar.stem}{chart.year_pillar.branch} ({chart.year_pillar.stem_korean}/{chart.year_pillar.branch_korean})",
        "month_pillar": f"{chart.month_pillar.stem}{chart.month_pillar.branch} ({chart.month_pillar.stem_korean}/{chart.month_pillar.branch_korean})",
        "day_pillar": f"{chart.day_pillar.stem}{chart.day_pillar.branch} ({chart.day_pillar.stem_korean}/{chart.day_pillar.branch_korean})",
        "hour_pillar": f"{chart.hour_pillar.stem}{chart.hour_pillar.branch}" if chart.hour_pillar else "Unknown",
        "day_master": f"{chart.day_pillar.stem} ({chart.day_stem_yin_yang} {chart.day_stem_element})",
        "five_elements": chart.five_elements,
        "dominant_element": chart.dominant_element,
        "weak_element": chart.weak_element,
        "animal_sign": chart.animal_sign,
        "lucky_color": chart.lucky_color,
        "lucky_direction": chart.lucky_direction,
        "lucky_number": chart.lucky_number,
    }
    
    return f"""Generate a premium Saju fortune report for a Cambodian user.

USER PROFILE:
{json.dumps(profile_data, ensure_ascii=False, indent=2)}

SAJU CHART (Four Pillars of Destiny):
{json.dumps(chart_data, ensure_ascii=False, indent=2)}

FOCUS AREA: {info.focus_area}

Generate monthly fortune for these 3 months: {months}

Requirements:
- Title should include the user's name and be inspiring
- Each section should be 2-4 sentences, practical and warm
- Monthly fortune should reflect seasonal energy and the user's chart
- Cambodia cultural note should reference local customs, Buddhist values, or Khmer New Year if relevant
- Action advice should be specific and achievable within 30 days
- Disclaimer must be clear that this is for entertainment and self-reflection only"""


def _fallback_report(info: BirthInfo, chart: SajuChart) -> PremiumReport:
    """API 키 없을 때 룰 기반 폴백 리포트"""
    dominant = chart.dominant_element
    weak = chart.weak_element
    day_elem = chart.day_stem_element
    
    element_descriptions = {
        "목": "Wood energy brings creativity, growth, and a pioneering spirit",
        "화": "Fire energy brings passion, charisma, and transformative power",
        "토": "Earth energy brings stability, reliability, and nurturing wisdom",
        "금": "Metal energy brings precision, discipline, and principled strength",
        "수": "Water energy brings intuition, adaptability, and deep wisdom",
    }
    
    today = date.today()
    monthly = []
    for i in range(3):
        m = today.month + i
        y = today.year
        if m > 12:
            m -= 12
            y += 1
        monthly.append(MonthlyFortune(
            year_month=f"{y}-{m:02d}",
            overall=f"A month of {['reflection', 'action', 'harvest'][i]} and growth for you.",
            key_events=[
                "Focus on strengthening key relationships",
                "New opportunities may arise in your career",
                "Financial planning will be rewarding",
            ],
            advice=f"Channel your {day_elem} energy positively this month.",
            lucky_period=f"The {'first' if i==0 else 'second' if i==1 else 'third'} week of the month is particularly favorable.",
        ))
    
    return PremiumReport(
        title=f"{info.name}'s Saju Destiny Report",
        personality=(
            f"Your Day Master is {chart.day_pillar.stem} ({chart.day_pillar.stem_korean}). "
            f"{element_descriptions.get(day_elem, 'Your energy is balanced and adaptable')}. "
            f"You tend to approach life with a {chart.day_stem_yin_yang} quality, "
            f"which gives you a unique perspective and natural strengths."
        ),
        strengths=(
            f"Your dominant {dominant} energy ({chart.five_elements.get(dominant, 0)} points in your chart) "
            f"is your greatest natural gift. Lean into this energy for career success and personal fulfillment. "
            f"Your animal sign — the {chart.animal_sign} — also brings specific strengths aligned with your life path."
        ),
        weaknesses=(
            f"Your {weak} energy is relatively weak in your chart, which may create occasional imbalances. "
            f"Be mindful of areas associated with {weak} element and actively work to strengthen them. "
            f"This is not a limitation but an opportunity for growth and self-development."
        ),
        love=(
            f"In relationships, your {day_elem} Day Master energy means you bring "
            f"{'creativity and passion' if day_elem in ['목','화'] else 'stability and loyalty' if day_elem in ['토','금'] else 'depth and intuition'} "
            f"to partnerships. Focus on open communication and mutual respect. "
            f"Your lucky color {chart.lucky_color} can be used as a positive signal in romantic contexts."
        ),
        career=(
            f"Your {dominant} dominant energy suggests natural talent in fields related to "
            f"{'creativity, education, or technology' if dominant in ['목','화'] else 'management, finance, or real estate' if dominant in ['토','금'] else 'communication, travel, or research'}. "
            f"The {chart.lucky_direction} direction may be favorable for career opportunities. "
            f"Consider exploring international opportunities that align with your strengths."
        ),
        money=(
            f"Your chart suggests a {'steady and growth-oriented' if dominant in ['목','토'] else 'dynamic and opportunity-driven'} approach to finances. "
            f"Lucky number {chart.lucky_number} can be a positive symbol in financial decisions. "
            f"Focus on building long-term wealth rather than seeking quick gains. "
            f"Always consult a qualified financial advisor for actual investment decisions."
        ),
        study_abroad=(
            f"Your chart shows {'strong' if chart.five_elements.get('목', 0) >= 2 else 'moderate'} potential for overseas opportunities. "
            f"International education and career pathways may be well-aligned with your {day_elem} energy. "
            f"Research scholarship programs and international exchange opportunities as concrete first steps."
        ),
        lucky_items=(
            f"Lucky color: {chart.lucky_color} — wear or use this color on important days. "
            f"Lucky direction: {chart.lucky_direction} — consider this when arranging your desk or bedroom. "
            f"Lucky number: {chart.lucky_number} — use for dates, phone numbers, or important choices. "
            f"Crystals or stones associated with {weak} element can help balance your energy."
        ),
        action_advice_30_days=[
            f"Wear or incorporate {chart.lucky_color} into your daily life as a positive energy reminder.",
            f"Write down 3 specific goals for the next 30 days and review them every morning.",
            f"Strengthen your {weak} element by adding related activities to your weekly routine.",
            f"Reach out to one person who can support your career or study goals this month.",
            f"Practice mindfulness or meditation for 10 minutes daily to balance your {dominant} energy.",
            f"Research one new opportunity that aligns with your interests and take one concrete step.",
        ],
        monthly_fortune=monthly,
        cambodia_cultural_note=(
            f"In Cambodian tradition, your {chart.animal_sign} sign carries specific cultural significance. "
            f"Consider visiting a local temple to make merit (Bun) on auspicious days, which aligns with your {dominant} energy. "
            f"The Khmer New Year (Chaul Chnam Thmey) is a particularly powerful time for you to set new intentions. "
            f"Combining Saju wisdom with Cambodian Buddhist values creates a powerful framework for life guidance."
        ),
        premium_disclaimer=(
            "This report is based on Saju (Four Pillars of Destiny) principles "
            "and is intended for entertainment and self-reflection purposes only. "
            "It does not constitute legal, medical, financial, immigration, or relationship advice. "
            "All major life decisions should be made in consultation with qualified professionals. "
            "Saju Destiny does not guarantee any outcomes described in this report."
        ),
    )


def generate_premium_report(info: BirthInfo, chart: SajuChart) -> Tuple[PremiumReport, str]:
    """OpenAI API를 사용하여 프리미엄 리포트 생성"""
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    if not api_key:
        return _fallback_report(info, chart), "local_fallback_no_api_key"
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": _build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": _build_user_prompt(info, chart),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=3000,
        )
        
        raw = response.choices[0].message.content
        data = json.loads(raw)
        
        # monthly_fortune 변환
        monthly_list = []
        for mf in data.get("monthly_fortune", []):
            monthly_list.append(MonthlyFortune(**mf))
        data["monthly_fortune"] = monthly_list
        
        return PremiumReport(**data), "openai_gpt"
    
    except Exception as exc:
        fallback = _fallback_report(info, chart)
        fallback.premium_disclaimer += f" (generation failed: {type(exc).__name__})"
        return fallback, f"local_fallback_error:{type(exc).__name__}"


def generate_daily_fortune(info: BirthInfo, chart: SajuChart, target_date: str = None) -> dict:
    """일별 운세 생성"""
    from datetime import date as dt
    today = dt.today() if not target_date else dt.fromisoformat(target_date)
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        # 룰 기반 폴백
        return {
            "date": str(today),
            "overall": f"A day of {['reflection', 'action', 'connection', 'creativity', 'rest', 'planning', 'celebration'][today.weekday()]} for your {chart.day_stem_element} energy.",
            "love": "Focus on honest communication with loved ones today.",
            "career": "Your focus and discipline will be rewarded today.",
            "money": "Be mindful of unnecessary expenses today.",
            "health": "Take time for physical activity and proper rest.",
            "lucky_color": chart.lucky_color,
            "lucky_number": chart.lucky_number,
        }
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        prompt = f"""Generate a daily fortune reading for {today.strftime('%A, %B %d, %Y')}.
User: {info.name}, Day Master: {chart.day_pillar.stem} ({chart.day_stem_element}), Animal: {chart.animal_sign}
Return JSON with keys: overall, love, career, money, health, lucky_color, lucky_number
Each value should be 1-2 sentences. Lucky color and number from the chart."""
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.8,
            max_tokens=400,
        )
        data = json.loads(response.choices[0].message.content)
        data["date"] = str(today)
        return data
    except Exception:
        return {
            "date": str(today),
            "overall": f"A day of balance and opportunity for your {chart.day_stem_element} energy.",
            "love": "Open your heart to meaningful connections today.",
            "career": "Steady progress brings lasting results.",
            "money": "Thoughtful decisions lead to financial stability.",
            "health": "Balance activity with adequate rest.",
            "lucky_color": chart.lucky_color,
            "lucky_number": chart.lucky_number,
        }
