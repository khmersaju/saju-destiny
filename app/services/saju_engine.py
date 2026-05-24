"""
AI Khmer Destiny - 만세력 계산 엔진
sajupy 라이브러리를 활용한 정확한 사주팔자 계산
캄보디아 프놈펜 UTC+7 시간대 및 경도 보정 지원
"""
from typing import Optional, Tuple, List
from datetime import date, datetime
import random

from sajupy import calculate_saju

from app.models import BirthInfo, SajuChart, Pillar


# ─── 천간(天干) 데이터 ───────────────────────────────────────────────────────────
STEM_DATA = {
    "甲": {"korean": "갑(甲)", "element": "목", "yin_yang": "양", "en": "Jia Wood+", "color": "green", "direction": "east"},
    "乙": {"korean": "을(乙)", "element": "목", "yin_yang": "음", "en": "Yi Wood-",  "color": "green", "direction": "east"},
    "丙": {"korean": "병(丙)", "element": "화", "yin_yang": "양", "en": "Bing Fire+","color": "red",   "direction": "south"},
    "丁": {"korean": "정(丁)", "element": "화", "yin_yang": "음", "en": "Ding Fire-","color": "red",   "direction": "south"},
    "戊": {"korean": "무(戊)", "element": "토", "yin_yang": "양", "en": "Wu Earth+", "color": "yellow","direction": "center"},
    "己": {"korean": "기(己)", "element": "토", "yin_yang": "음", "en": "Ji Earth-", "color": "yellow","direction": "center"},
    "庚": {"korean": "경(庚)", "element": "금", "yin_yang": "양", "en": "Geng Metal+","color": "white","direction": "west"},
    "辛": {"korean": "신(辛)", "element": "금", "yin_yang": "음", "en": "Xin Metal-","color": "white", "direction": "west"},
    "壬": {"korean": "임(壬)", "element": "수", "yin_yang": "양", "en": "Ren Water+","color": "black", "direction": "north"},
    "癸": {"korean": "계(癸)", "element": "수", "yin_yang": "음", "en": "Gui Water-","color": "black", "direction": "north"},
}

# ─── 지지(地支) 데이터 ───────────────────────────────────────────────────────────
BRANCH_DATA = {
    "子": {"korean": "자(子)", "animal": "쥐(Rat)",    "element": "수", "en": "Zi Rat"},
    "丑": {"korean": "축(丑)", "animal": "소(Ox)",     "element": "토", "en": "Chou Ox"},
    "寅": {"korean": "인(寅)", "animal": "호랑이(Tiger)","element": "목","en": "Yin Tiger"},
    "卯": {"korean": "묘(卯)", "animal": "토끼(Rabbit)","element": "목","en": "Mao Rabbit"},
    "辰": {"korean": "진(辰)", "animal": "용(Dragon)", "element": "토", "en": "Chen Dragon"},
    "巳": {"korean": "사(巳)", "animal": "뱀(Snake)",  "element": "화", "en": "Si Snake"},
    "午": {"korean": "오(午)", "animal": "말(Horse)",  "element": "화", "en": "Wu Horse"},
    "未": {"korean": "미(未)", "animal": "양(Goat)",   "element": "토", "en": "Wei Goat"},
    "申": {"korean": "신(申)", "animal": "원숭이(Monkey)","element": "금","en": "Shen Monkey"},
    "酉": {"korean": "유(酉)", "animal": "닭(Rooster)","element": "금", "en": "You Rooster"},
    "戌": {"korean": "술(戌)", "animal": "개(Dog)",    "element": "토", "en": "Xu Dog"},
    "亥": {"korean": "해(亥)", "animal": "돼지(Pig)",  "element": "수", "en": "Hai Pig"},
}

# ─── 오행 행운 데이터 ────────────────────────────────────────────────────────────
ELEMENT_LUCKY = {
    "목": {"color": "Green (초록)", "direction": "East (동쪽)", "number": 3, "season": "Spring"},
    "화": {"color": "Red (빨강)",   "direction": "South (남쪽)", "number": 9, "season": "Summer"},
    "토": {"color": "Yellow (노랑)","direction": "Center (중앙)","number": 5, "season": "All seasons"},
    "금": {"color": "White (흰색)", "direction": "West (서쪽)",  "number": 4, "season": "Autumn"},
    "수": {"color": "Black/Blue (검정/파랑)","direction": "North (북쪽)","number": 1,"season": "Winter"},
}

# ─── 캄보디아 도시 경도 데이터 ──────────────────────────────────────────────────
CAMBODIA_CITIES = {
    "Phnom Penh":  {"longitude": 104.9282, "utc_offset": 7.0},
    "Siem Reap":   {"longitude": 103.8597, "utc_offset": 7.0},
    "Battambang":  {"longitude": 103.1990, "utc_offset": 7.0},
    "Sihanoukville":{"longitude": 103.5225,"utc_offset": 7.0},
    "Kampot":      {"longitude": 104.1814, "utc_offset": 7.0},
    "Kratie":      {"longitude": 106.0186, "utc_offset": 7.0},
}


def _build_pillar(stem: str, branch: str, pillar_name: str) -> Pillar:
    """천간과 지지로 사주 기둥 객체 생성"""
    stem_info = STEM_DATA.get(stem, {})
    branch_info = BRANCH_DATA.get(branch, {})
    
    return Pillar(
        stem=stem,
        branch=branch,
        stem_korean=stem_info.get("korean", stem),
        branch_korean=branch_info.get("animal", branch_info.get("korean", branch)),
        element=stem_info.get("element", "?"),
        yin_yang=stem_info.get("yin_yang", "?"),
        pillar_name=pillar_name,
    )


def calculate_saju_chart(info: BirthInfo) -> SajuChart:
    """
    sajupy 라이브러리를 사용하여 정확한 사주팔자 계산
    캄보디아 현지 시간대(UTC+7) 및 경도 보정 적용
    """
    # 도시 경도 자동 조회
    city_data = CAMBODIA_CITIES.get(info.city, CAMBODIA_CITIES["Phnom Penh"])
    longitude = info.longitude or city_data["longitude"]
    utc_offset = info.utc_offset or city_data["utc_offset"]
    
    # 출생 시간 처리
    birth_hour = info.birth_hour if info.birth_hour is not None else 12  # 모를 경우 정오로 설정
    birth_minute = info.birth_minute or 0
    
    # sajupy로 사주 계산 (태양시 보정 적용)
    result = calculate_saju(
        year=info.birth_year,
        month=info.birth_month,
        day=info.birth_day,
        hour=birth_hour,
        minute=birth_minute,
        longitude=longitude,
        use_solar_time=True,
        utc_offset=utc_offset,
        early_zi_time=True,  # 자시(23:00-01:00) 조기 처리
    )
    
    # 기둥 생성
    year_pillar = _build_pillar(result["year_stem"], result["year_branch"], "년주(年柱)")
    month_pillar = _build_pillar(result["month_stem"], result["month_branch"], "월주(月柱)")
    day_pillar = _build_pillar(result["day_stem"], result["day_branch"], "일주(日柱)")
    
    hour_pillar = None
    if info.birth_hour is not None:
        hour_pillar = _build_pillar(result["hour_stem"], result["hour_branch"], "시주(時柱)")
    
    # 오행 분포 계산
    elements = {"목": 0, "화": 0, "토": 0, "금": 0, "수": 0}
    pillars_to_count = [year_pillar, month_pillar, day_pillar]
    if hour_pillar:
        pillars_to_count.append(hour_pillar)
    
    for pillar in pillars_to_count:
        stem_elem = STEM_DATA.get(pillar.stem, {}).get("element")
        branch_elem = BRANCH_DATA.get(pillar.branch, {}).get("element")
        if stem_elem in elements:
            elements[stem_elem] += 1
        if branch_elem in elements:
            elements[branch_elem] += 1
    
    # 주도/약한 오행
    dominant = max(elements, key=elements.get)
    weak = min(elements, key=elements.get)
    
    # 일간 정보
    day_stem_data = STEM_DATA.get(day_pillar.stem, {})
    day_stem_element = day_stem_data.get("element", "?")
    day_stem_yin_yang = day_stem_data.get("yin_yang", "?")
    
    # 행운 데이터 (약한 오행을 보완하는 방향으로 설정)
    lucky_data = ELEMENT_LUCKY.get(weak, ELEMENT_LUCKY["목"])
    
    # 띠 계산
    year_branch = result["year_branch"]
    animal_sign = BRANCH_DATA.get(year_branch, {}).get("animal", "?")
    
    # 계산 참고사항
    solar_correction = result.get("solar_correction")
    note = f"Calculated using sajupy library. Location: {info.city} (lon={longitude:.4f}, UTC+{utc_offset})"
    if solar_correction:
        note += f". Solar time correction: {solar_correction.get('correction_minutes', 0):.1f} min"
    if info.birth_hour is None:
        note += ". Birth hour unknown; hour pillar not calculated."
    
    return SajuChart(
        year_pillar=year_pillar,
        month_pillar=month_pillar,
        day_pillar=day_pillar,
        hour_pillar=hour_pillar,
        five_elements=elements,
        dominant_element=dominant,
        weak_element=weak,
        day_stem_element=day_stem_element,
        day_stem_yin_yang=day_stem_yin_yang,
        lucky_color=lucky_data["color"],
        lucky_direction=lucky_data["direction"],
        lucky_number=lucky_data["number"],
        animal_sign=animal_sign,
        calculation_note=note,
    )


def build_free_summary(info: BirthInfo, chart: SajuChart) -> Tuple[str, List[str]]:
    """무료 기본 운세 요약 생성 (룰 기반)"""
    dominant = chart.dominant_element
    weak = chart.weak_element
    day_elem = chart.day_stem_element
    yin_yang = chart.day_stem_yin_yang
    
    # 오행별 성격 특성
    element_personality = {
        "목": "creative, growth-oriented, and idealistic. You have strong leadership potential and a natural drive to start new things.",
        "화": "passionate, expressive, and charismatic. You bring warmth and energy to every situation you enter.",
        "토": "stable, reliable, and nurturing. People trust you naturally, and you excel at bringing harmony to groups.",
        "금": "precise, disciplined, and principled. You have a strong sense of justice and excel in structured environments.",
        "수": "intuitive, adaptable, and wise. You have deep emotional intelligence and the ability to flow through challenges.",
    }
    
    # 행운의 색상 영어 설명
    element_color_advice = {
        "목": "Wearing green or surrounding yourself with plants can enhance your natural energy.",
        "화": "Red and orange tones can amplify your passionate nature and attract positive attention.",
        "토": "Earth tones like yellow, brown, and beige help ground your energy and attract stability.",
        "금": "White and metallic colors strengthen your focus and attract clarity in decisions.",
        "수": "Deep blue and black help deepen your intuition and attract wisdom.",
    }
    
    personality_desc = element_personality.get(day_elem, "balanced and adaptable")
    
    summary = (
        f"Based on your Korean Saju (Four Pillars) chart, your Day Master is {chart.day_pillar.stem} "
        f"({chart.day_pillar.stem_korean}), representing {yin_yang} {day_elem} energy. "
        f"This means you are naturally {personality_desc} "
        f"Your chart shows a strong presence of {dominant} energy "
        f"({chart.five_elements.get(dominant, 0)} points), which shapes your dominant tendencies. "
        f"Your {weak} energy is relatively weaker, suggesting areas for growth and balance. "
        f"Your animal sign is the {chart.animal_sign}."
    )
    
    advice = [
        f"Your lucky color is {chart.lucky_color}. {element_color_advice.get(weak, '')}",
        f"Your lucky direction is {chart.lucky_direction}. Consider this when arranging your workspace or home.",
        f"Your lucky number is {chart.lucky_number}. Use it for important decisions or dates.",
        f"To balance your {weak} energy, incorporate activities associated with {weak} element into your daily life.",
        f"Your strongest energy ({dominant}) is your natural gift — lean into it for career and personal growth.",
    ]
    
    return summary, advice


def get_today_fortune(chart: SajuChart) -> str:
    """오늘의 운세 (간단한 룰 기반)"""
    today = date.today()
    day_of_week = today.weekday()  # 0=월요일
    
    fortunes = {
        "목": [
            "Today is a good day for new beginnings and creative projects. Trust your instincts.",
            "Your natural growth energy is strong today. Take initiative in relationships and work.",
            "Focus on long-term goals today. Plant seeds that will grow into future success.",
        ],
        "화": [
            "Your passionate energy shines today. Express yourself boldly in social situations.",
            "Today favors communication and networking. Reach out to someone you've been meaning to contact.",
            "Your charisma is at its peak. Use it to inspire others and advance your goals.",
        ],
        "토": [
            "Stability and reliability are your strengths today. Focus on building solid foundations.",
            "Today is ideal for resolving conflicts and bringing harmony to your relationships.",
            "Your nurturing energy is powerful. Help someone who needs support today.",
        ],
        "금": [
            "Precision and discipline will serve you well today. Focus on details and quality.",
            "Today is good for making important decisions. Your judgment is sharp and clear.",
            "Your sense of justice is heightened. Stand up for what is right today.",
        ],
        "수": [
            "Your intuition is particularly strong today. Trust your inner voice in important matters.",
            "Today favors reflection and deep thinking. Take time to meditate or journal.",
            "Your adaptability is your greatest asset today. Go with the flow and embrace change.",
        ],
    }
    
    elem_fortunes = fortunes.get(chart.day_stem_element, fortunes["토"])
    # 날짜 기반으로 일관된 선택 (같은 날 같은 운세)
    idx = (today.day + today.month) % len(elem_fortunes)
    return elem_fortunes[idx]
