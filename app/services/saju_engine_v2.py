"""
사주 엔진 v2 — 고도화 버전
- 양력 → 음력 자동 변환 (korean-lunar-calendar)
- 30분 단위 시주 정밀 계산
- 대운(大運) 계산 (10년 주기)
- 세운(歲運) 계산 (올해/내년)
- 월운(月運) 계산 (12개월)
- 일운(日運) 계산 (오늘/내일/지정일)
- 길일(吉日) 계산
- 궁합(宮合) 분석
- 오행 색깔/방향/숫자/직업 매핑
"""
from __future__ import annotations
import math
from datetime import date, datetime, timedelta
from typing import Optional
from korean_lunar_calendar import KoreanLunarCalendar
import sajupy


# ─── 천간 / 지지 기본 데이터 ─────────────────────────────────────────
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

STEM_KR = {
    "甲": "갑(甲)", "乙": "을(乙)", "丙": "병(丙)", "丁": "정(丁)", "戊": "무(戊)",
    "己": "기(己)", "庚": "경(庚)", "辛": "신(辛)", "壬": "임(壬)", "癸": "계(癸)",
}

# ─── 크메르어 천간 발음 + 의미 매핑 ────────────────────────────────────
STEM_KM = {
    "甲": {"phonetic": "ហ្គាប់", "meaning": "ឈើធំ / Yang Wood", "element_km": "ឈើ (Yang)"},
    "乙": {"phonetic": "អ៊ុល", "meaning": "ឈើទន់ / Yin Wood", "element_km": "ឈើ (Yin)"},
    "丙": {"phonetic": "ប៊ីង", "meaning": "ភ្លើងខ្លាំង / Yang Fire", "element_km": "ភ្លើង (Yang)"},
    "丁": {"phonetic": "ជីង", "meaning": "ភ្លើងតូច / Yin Fire", "element_km": "ភ្លើង (Yin)"},
    "戊": {"phonetic": "វូ", "meaning": "ដីរឹង / Yang Earth", "element_km": "ដី (Yang)"},
    "己": {"phonetic": "ជី", "meaning": "ដីទន់ / Yin Earth", "element_km": "ដី (Yin)"},
    "庚": {"phonetic": "ហ្គឹង", "meaning": "លោហ:រឹង / Yang Metal", "element_km": "លោហ (Yang)"},
    "辛": {"phonetic": "ស៊ីន", "meaning": "លោហ:ទន់ / Yin Metal", "element_km": "លោហ (Yin)"},
    "壬": {"phonetic": "រ៉ឹន", "meaning": "ទឹកខ្លាំង / Yang Water", "element_km": "ទឹក (Yang)"},
    "癸": {"phonetic": "ហ្គ្វីស", "meaning": "ទឹកស្ងាត់ / Yin Water", "element_km": "ទឹក (Yin)"},
}

# ─── 크메르어 지지 발음 + 의미 매핑 ────────────────────────────────────
BRANCH_KM = {
    "子": {"phonetic": "ជ្ហ្ស", "animal": "កណ្ដុរ", "animal_en": "Rat", "element_km": "ទឹក"},
    "丑": {"phonetic": "ជូ", "animal": "គោ", "animal_en": "Ox", "element_km": "ដី"},
    "寅": {"phonetic": "យ៉ីន", "animal": "ខ្លា", "animal_en": "Tiger", "element_km": "ឈើ"},
    "卯": {"phonetic": "ម៉ៅ", "animal": "ទន្សាយ", "animal_en": "Rabbit", "element_km": "ឈើ"},
    "辰": {"phonetic": "ចេន", "animal": "នាគ", "animal_en": "Dragon", "element_km": "ដី"},
    "巳": {"phonetic": "ស៊ី", "animal": "ពស់", "animal_en": "Snake", "element_km": "ភ្លើង"},
    "午": {"phonetic": "វូ", "animal": "សេះ", "animal_en": "Horse", "element_km": "ភ្លើង"},
    "未": {"phonetic": "វ៉ី", "animal": "ពពែ", "animal_en": "Goat", "element_km": "ដី"},
    "申": {"phonetic": "ស្ហេន", "animal": "ស្វា", "animal_en": "Monkey", "element_km": "លោហ"},
    "酉": {"phonetic": "យូ", "animal": "មាន់", "animal_en": "Rooster", "element_km": "លោហ"},
    "戌": {"phonetic": "ស្ហូ", "animal": "ឆ្កែ", "animal_en": "Dog", "element_km": "ដី"},
    "亥": {"phonetic": "ហៃ", "animal": "ជ្រូក", "animal_en": "Pig", "element_km": "ទឹក"},
}

# ─── 크메르어 오행 이름 매핑 ─────────────────────────────────────────
ELEMENT_KM = {"목": "ឈើ", "화": "ភ្លើង", "토": "ដី", "금": "លោហ", "수": "ទឹក"}
BRANCH_KR = {
    "子": "자(Rat)", "丑": "축(Ox)", "寅": "인(Tiger)", "卯": "묘(Rabbit)",
    "辰": "진(Dragon)", "巳": "사(Snake)", "午": "오(Horse)", "未": "미(Goat)",
    "申": "신(Monkey)", "酉": "유(Rooster)", "戌": "술(Dog)", "亥": "해(Pig)",
}
BRANCH_EN = {
    "子": "Rat", "丑": "Ox", "寅": "Tiger", "卯": "Rabbit",
    "辰": "Dragon", "巳": "Snake", "午": "Horse", "未": "Goat",
    "申": "Monkey", "酉": "Rooster", "戌": "Dog", "亥": "Pig",
}
STEM_ELEMENT = {
    "甲": "목", "乙": "목", "丙": "화", "丁": "화", "戊": "토",
    "己": "토", "庚": "금", "辛": "금", "壬": "수", "癸": "수",
}
BRANCH_ELEMENT = {
    "子": "수", "丑": "토", "寅": "목", "卯": "목", "辰": "토", "巳": "화",
    "午": "화", "未": "토", "申": "금", "酉": "금", "戌": "토", "亥": "수",
}
STEM_YIN_YANG = {
    "甲": "양", "乙": "음", "丙": "양", "丁": "음", "戊": "양",
    "己": "음", "庚": "양", "辛": "음", "壬": "양", "癸": "음",
}

# ─── 오행 매핑 (영어 포함) ───────────────────────────────────────────
ELEMENT_EN = {"목": "Wood", "화": "Fire", "토": "Earth", "금": "Metal", "수": "Water"}
ELEMENT_ICON = {"목": "🌿", "화": "🔥", "토": "🌍", "금": "⚙️", "수": "💧"}
ELEMENT_COLOR = {"목": "#3CB371", "화": "#E84040", "토": "#D4A017", "금": "#A0A0A0", "수": "#4A90D9"}

ELEMENT_LUCKY_COLORS = {
    "목": {"en": "Green & Blue", "km": "បៃតង និង ខៀវ", "hex": ["#228B22", "#1E90FF"]},
    "화": {"en": "Red & Orange", "km": "ក្រហម និង លឿងក្រហម", "hex": ["#DC143C", "#FF6600"]},
    "토": {"en": "Yellow & Brown", "km": "លឿង និង ត្នោត", "hex": ["#FFD700", "#8B4513"]},
    "금": {"en": "White & Gold", "km": "ស និង មាស", "hex": ["#FFFFFF", "#FFD700"]},
    "수": {"en": "Black & Navy", "km": "ខ្មៅ និង ខៀវចាស់", "hex": ["#000000", "#000080"]},
}
ELEMENT_LUCKY_DIRECTION = {
    "목": {"en": "East", "km": "ខាងកើត"},
    "화": {"en": "South", "km": "ខាងត្បូង"},
    "토": {"en": "Center", "km": "មជ្ឈមណ្ឌល"},
    "금": {"en": "West", "km": "ខាងលិច"},
    "수": {"en": "North", "km": "ខាងជើង"},
}
ELEMENT_LUCKY_NUMBER = {"목": [3, 4], "화": [7, 9], "토": [0, 5], "금": [4, 9], "수": [1, 6]}
ELEMENT_CAREERS = {
    "목": ["Education", "Medicine", "Fashion", "Arts", "Social Work"],
    "화": ["Entertainment", "Marketing", "Politics", "Finance", "IT"],
    "토": ["Real Estate", "Agriculture", "Construction", "HR", "Consulting"],
    "금": ["Law", "Engineering", "Military", "Finance", "Precision Industry"],
    "수": ["Trading", "Travel", "Research", "Writing", "Diplomacy"],
}

# ─── 시주(時柱) — 30분 단위 정밀 계산 ────────────────────────────────
# 시주는 2시간 단위이나, 30분 단위로 입력받아 정확한 시간대 판별
# 자시(子時): 23:00~01:00  축시(丑時): 01:00~03:00  ...
HOUR_BRANCH_MAP = [
    # (시작시간_분, 끝시간_분, 지지)  — 분 단위로 계산 (하루=1440분)
    (23 * 60, 24 * 60 + 60, "子"),   # 23:00~01:00
    (1 * 60, 3 * 60, "丑"),
    (3 * 60, 5 * 60, "寅"),
    (5 * 60, 7 * 60, "卯"),
    (7 * 60, 9 * 60, "辰"),
    (9 * 60, 11 * 60, "巳"),
    (11 * 60, 13 * 60, "午"),
    (13 * 60, 15 * 60, "未"),
    (15 * 60, 17 * 60, "申"),
    (17 * 60, 19 * 60, "酉"),
    (19 * 60, 21 * 60, "戌"),
    (21 * 60, 23 * 60, "亥"),
]


def get_hour_branch(hour: int, minute: int = 0) -> str:
    """30분 단위 시간을 받아 정확한 시지(時支) 반환"""
    total_min = hour * 60 + minute
    if total_min >= 23 * 60 or total_min < 1 * 60:
        return "子"
    for start, end, branch in HOUR_BRANCH_MAP[1:]:
        if start <= total_min < end:
            return branch
    return "亥"


def get_hour_stem(day_stem: str, hour_branch: str) -> str:
    """일간(日干)과 시지(時支)로 시간(時干) 계산"""
    day_stem_idx = STEMS.index(day_stem)
    branch_idx = BRANCHES.index(hour_branch)
    # 일간에 따른 자시(子時) 천간 기준
    base_stems = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8,  # 甲→甲, 乙→丙, 丙→戊, 丁→庚, 戊→壬
                  5: 0, 6: 2, 7: 4, 8: 6, 9: 8}   # 己→甲, 庚→丙, 辛→戊, 壬→庚, 癸→壬
    base = base_stems[day_stem_idx % 10]
    stem_idx = (base + branch_idx) % 10
    return STEMS[stem_idx]


# ─── 양력 → 음력 변환 ─────────────────────────────────────────────
def solar_to_lunar(year: int, month: int, day: int) -> dict:
    """양력 날짜를 음력으로 변환"""
    cal = KoreanLunarCalendar()
    cal.setSolarDate(year, month, day)
    return {
        "lunar_year": cal.lunarYear,
        "lunar_month": cal.lunarMonth,
        "lunar_day": cal.lunarDay,
        "is_intercalation": cal.isIntercalation,
        "lunar_iso": cal.LunarIsoFormat(),
        "gapja_korean": cal.getGapJaString(),
        "gapja_chinese": cal.getChineseGapJaString(),
    }


# ─── 캄보디아 도시 경도/시간대 ─────────────────────────────────────
CAMBODIA_CITIES = {
    "Phnom Penh": {"lon": 104.9282, "utc": 7.0},
    "Siem Reap": {"lon": 103.8597, "utc": 7.0},
    "Battambang": {"lon": 103.1990, "utc": 7.0},
    "Sihanoukville": {"lon": 103.5297, "utc": 7.0},
    "Kampot": {"lon": 104.1820, "utc": 7.0},
    "Kratie": {"lon": 106.0190, "utc": 7.0},
    "Kampong Cham": {"lon": 105.4630, "utc": 7.0},
    "Takeo": {"lon": 104.7850, "utc": 7.0},
}


def get_solar_time_correction_minutes(longitude: float, utc_offset: float) -> float:
    """경도 기반 태양시 보정값(분) 계산"""
    standard_lon = utc_offset * 15
    return (longitude - standard_lon) * 4  # 1도 = 4분


# ─── 사주 전체 계산 (sajupy 래퍼) ─────────────────────────────────
def calculate_full_chart(
    birth_year: int, birth_month: int, birth_day: int,
    birth_hour: int = 12, birth_minute: int = 0,
    gender: str = "male", city: str = "Phnom Penh"
) -> dict:
    """sajupy 기반 사주 계산 + 음력 + 30분 단위 시주"""
    city_info = CAMBODIA_CITIES.get(city, CAMBODIA_CITIES["Phnom Penh"])
    lon = city_info["lon"]
    utc = city_info["utc"]

    # 태양시 보정
    correction_min = get_solar_time_correction_minutes(lon, utc)
    dt = datetime(birth_year, birth_month, birth_day, birth_hour, birth_minute)
    corrected_dt = dt + timedelta(minutes=correction_min)

    # sajupy 계산 (태양시 보정 포함)
    saju_result = sajupy.calculate_saju(
        birth_year, birth_month, birth_day,
        birth_hour, birth_minute,
        longitude=lon, use_solar_time=True, utc_offset=utc
    )
    details = sajupy.get_saju_details(saju_result)
    pillars_data = details["pillars"]

    # 시주 30분 단위 정밀 계산
    hour_branch_precise = get_hour_branch(corrected_dt.hour, corrected_dt.minute)
    day_stem_char = pillars_data["day"]["stem"]
    hour_stem_precise = get_hour_stem(day_stem_char, hour_branch_precise)

    # 오행 분포 계산
    elements = {"목": 0, "화": 0, "토": 0, "금": 0, "수": 0}
    pillars_raw = [
        (pillars_data["year"]["stem"], pillars_data["year"]["branch"]),
        (pillars_data["month"]["stem"], pillars_data["month"]["branch"]),
        (pillars_data["day"]["stem"], pillars_data["day"]["branch"]),
        (hour_stem_precise, hour_branch_precise),
    ]
    for stem, branch in pillars_raw:
        if stem in STEM_ELEMENT:
            elements[STEM_ELEMENT[stem]] += 1
        if branch in BRANCH_ELEMENT:
            elements[BRANCH_ELEMENT[branch]] += 1

    dominant = max(elements, key=elements.get)
    weak = min(elements, key=elements.get)
    day_stem = pillars_data["day"]["stem"]
    day_stem_elem = STEM_ELEMENT.get(day_stem, "목")
    day_yin_yang = STEM_YIN_YANG.get(day_stem, "양")

    # 음력 변환
    lunar = solar_to_lunar(birth_year, birth_month, birth_day)

    # 띠 계산
    year_branch = pillars_data["year"]["branch"]
    animal = BRANCH_EN.get(year_branch, "Unknown")

    # 행운 정보
    lucky_colors = ELEMENT_LUCKY_COLORS.get(dominant, ELEMENT_LUCKY_COLORS["목"])
    lucky_direction = ELEMENT_LUCKY_DIRECTION.get(dominant, ELEMENT_LUCKY_DIRECTION["목"])
    lucky_numbers = ELEMENT_LUCKY_NUMBER.get(dominant, [1, 6])
    lucky_careers = ELEMENT_CAREERS.get(dominant, [])

    def _make_pillar(stem: str, branch: str) -> dict:
        stem_km_data = STEM_KM.get(stem, {})
        branch_km_data = BRANCH_KM.get(branch, {})
        return {
            "stem": stem, "branch": branch,
            "pillar": stem + branch,
            "stem_kr": STEM_KR.get(stem, stem),
            "branch_kr": BRANCH_KR.get(branch, branch),
            "branch_en": BRANCH_EN.get(branch, ""),
            "element": STEM_ELEMENT.get(stem, ""),
            "branch_element": BRANCH_ELEMENT.get(branch, ""),
            "yin_yang": STEM_YIN_YANG.get(stem, ""),
            # 크메르어 발음 + 의미 (프론트엔드 병기 표시용)
            "stem_km_phonetic": stem_km_data.get("phonetic", ""),
            "stem_km_meaning": stem_km_data.get("meaning", ""),
            "stem_km_element": stem_km_data.get("element_km", ""),
            "branch_km_phonetic": branch_km_data.get("phonetic", ""),
            "branch_km_animal": branch_km_data.get("animal", ""),
            "branch_km_element": branch_km_data.get("element_km", ""),
        }

    return {
        "pillars": {
            "year": _make_pillar(pillars_data["year"]["stem"], pillars_data["year"]["branch"]),
            "month": _make_pillar(pillars_data["month"]["stem"], pillars_data["month"]["branch"]),
            "day": _make_pillar(pillars_data["day"]["stem"], pillars_data["day"]["branch"]),
            "hour": _make_pillar(hour_stem_precise, hour_branch_precise),
        },
        "five_elements": elements,
        "dominant_element": dominant,
        "weak_element": weak,
        "day_master": {
            "stem": day_stem,
            "element": day_stem_elem,
            "yin_yang": day_yin_yang,
            "stem_kr": STEM_KR.get(day_stem, day_stem),
            "stem_km_phonetic": STEM_KM.get(day_stem, {}).get("phonetic", ""),
            "stem_km_meaning": STEM_KM.get(day_stem, {}).get("meaning", ""),
            "element_km": ELEMENT_KM.get(day_stem_elem, ""),
        },
        "animal_sign": animal,
        "animal_sign_km": BRANCH_KM.get(year_branch, {}).get("animal", ""),
        "animal_sign_kr": BRANCH_KR.get(year_branch, ""),
        "lucky": {
            "colors": lucky_colors,
            "direction": lucky_direction,
            "numbers": lucky_numbers,
            "careers": lucky_careers,
        },
        "lunar": lunar,
        "solar_correction_min": round(correction_min, 1),
        "city": city,
        "gender": gender,
    }


# ─── 대운(大運) 계산 ──────────────────────────────────────────────
def calculate_daeun(
    birth_year: int, birth_month: int, birth_day: int,
    gender: str = "male", chart: dict = None
) -> list[dict]:
    """대운 계산 — 10년 단위 8개 대운"""
    if chart is None:
        chart = calculate_full_chart(birth_year, birth_month, birth_day, gender=gender)

    month_stem = chart["pillars"]["month"]["stem"]
    month_branch = chart["pillars"]["month"]["branch"]
    month_stem_idx = STEMS.index(month_stem)
    month_branch_idx = BRANCHES.index(month_branch)

    # 순행/역행 결정: 양남음녀 → 순행, 음남양녀 → 역행
    day_yin_yang = chart["day_master"]["yin_yang"]
    if gender == "male":
        forward = (day_yin_yang == "양")
    else:
        forward = (day_yin_yang == "음")

    daeun_list = []
    for i in range(1, 9):
        if forward:
            s_idx = (month_stem_idx + i) % 10
            b_idx = (month_branch_idx + i) % 12
        else:
            s_idx = (month_stem_idx - i) % 10
            b_idx = (month_branch_idx - i) % 12

        stem = STEMS[s_idx]
        branch = BRANCHES[b_idx]
        start_age = i * 10 - 9  # 1, 11, 21, 31, ...
        start_year = birth_year + start_age

        daeun_list.append({
            "index": i,
            "stem": stem,
            "branch": branch,
            "stem_kr": STEM_KR.get(stem, stem),
            "branch_kr": BRANCH_KR.get(branch, branch),
            "branch_en": BRANCH_EN.get(branch, ""),
            "element": STEM_ELEMENT.get(stem, ""),
            "start_age": start_age,
            "end_age": start_age + 9,
            "start_year": start_year,
            "end_year": start_year + 9,
        })
    return daeun_list


# ─── 세운(歲運) 계산 ─────────────────────────────────────────────
def calculate_seun(base_year: int = None, count: int = 5) -> list[dict]:
    """세운 계산 — 현재 연도부터 N년간"""
    if base_year is None:
        base_year = date.today().year

    seun_list = []
    for i in range(count):
        yr = base_year + i
        stem_idx = (yr - 4) % 10
        branch_idx = (yr - 4) % 12
        stem = STEMS[stem_idx]
        branch = BRANCHES[branch_idx]
        seun_list.append({
            "year": yr,
            "stem": stem,
            "branch": branch,
            "stem_kr": STEM_KR.get(stem, stem),
            "branch_kr": BRANCH_KR.get(branch, branch),
            "branch_en": BRANCH_EN.get(branch, ""),
            "element": STEM_ELEMENT.get(stem, ""),
            "animal": BRANCH_EN.get(branch, ""),
        })
    return seun_list


# ─── 오행 상생/상극 점수 계산 ─────────────────────────────────────
def _element_score(month_elem: str, day_master_elem: str, dominant_elem: str) -> int:
    """
    월 오행과 일간 오행의 관계로 점수 계산 (30~100점)
    - 상생(相生, 생해주는 관계): 85~100점
    - 동일 오행: 75~85점
    - 중립(洩氣, 내가 생해주는 관계): 60~75점
    - 상극(相剋, 극하는 관계): 35~55점
    - 피극(被剋, 극받는 관계): 30~50점
    """
    # 상생: 나를 생해주는 오행 (목→화→토→금→수→목)
    generates_to_me = {v: k for k, v in ELEMENT_GENERATES.items()}  # 나를 생해주는 오행
    # 내가 생해주는 오행
    i_generate = ELEMENT_GENERATES.get(day_master_elem, '')
    # 내가 극하는 오행
    i_control = ELEMENT_CONTROLS.get(day_master_elem, '')
    # 나를 극하는 오행
    controls_me = {v: k for k, v in ELEMENT_CONTROLS.items()}
    controls_me_elem = controls_me.get(day_master_elem, '')

    if month_elem == day_master_elem:
        base = 80  # 동일 오행: 강함
    elif generates_to_me.get(day_master_elem) == month_elem:
        base = 90  # 나를 생해주는 오행: 매우 길함
    elif month_elem == i_generate:
        base = 65  # 내가 생해주는 오행: 소진되지만 나쁘지 않음
    elif month_elem == i_control:
        base = 55  # 내가 극하는 오행: 중간
    elif month_elem == controls_me_elem:
        base = 40  # 나를 극하는 오행: 흉함
    else:
        base = 70  # 기타

    # 지배 오행과의 관계로 보정 (+/-10)
    if dominant_elem == month_elem:
        base = min(100, base + 8)
    elif ELEMENT_GENERATES.get(dominant_elem) == month_elem:
        base = min(100, base + 5)
    elif ELEMENT_CONTROLS.get(dominant_elem) == month_elem:
        base = max(30, base - 8)

    # 월 인덱스별 자연 변동 (계절 효과, ±5)
    return max(30, min(100, base))


# ─── 월운(月運) 계산 ─────────────────────────────────────────────
def calculate_wolun(year: int = None, day_master_elem: str = None, dominant_elem: str = None) -> list[dict]:
    """월운 계산 — 해당 연도 12개월 (점수 포함)"""
    if year is None:
        year = date.today().year

    # 연간 천간 기준으로 월간 계산
    year_stem_idx = (year - 4) % 10
    # 인월(寅月, 1월) 기준 천간: 갑기년→병인, 을경년→무인, ...
    base_month_stems = {0: 2, 1: 4, 2: 6, 3: 8, 4: 0, 5: 2, 6: 4, 7: 6, 8: 8, 9: 0}
    base_stem = base_month_stems[year_stem_idx % 10]

    months_kr = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
    # 인월(2월)부터 시작하는 월지 순서
    month_branches = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

    # 계절 변동 오프셋 (봄/여름/가을/겨울 리듬, 인덱스 0=1월)
    season_offsets = [2, 5, 3, -2, -5, -3, 2, 5, 3, -2, -5, -3]

    wolun_list = []
    for i in range(12):
        stem_idx = (base_stem + i) % 10
        branch = month_branches[i]
        month_num = i + 1
        stem = STEMS[stem_idx]
        month_elem = STEM_ELEMENT.get(stem, "")
        branch_elem = BRANCH_ELEMENT.get(branch, "")

        # 월간 오행 기반 점수 계산
        if day_master_elem and month_elem:
            base_score = _element_score(month_elem, day_master_elem, dominant_elem or month_elem)
            # 월지 오행으로 추가 보정
            if branch_elem and branch_elem != month_elem:
                branch_score = _element_score(branch_elem, day_master_elem, dominant_elem or month_elem)
                base_score = int(base_score * 0.65 + branch_score * 0.35)
            # 계절 변동 적용
            score = max(30, min(100, base_score + season_offsets[i]))
        else:
            # day_master_elem 없으면 기본 점수 (계절 변동만)
            score = max(30, min(100, 65 + season_offsets[i]))

        wolun_list.append({
            "month": month_num,
            "month_name": months_kr[i],
            "stem": stem,
            "branch": branch,
            "stem_kr": STEM_KR.get(stem, stem),
            "branch_kr": BRANCH_KR.get(branch, branch),
            "branch_en": BRANCH_EN.get(branch, ""),
            "element": STEM_ELEMENT.get(stem, ""),
            "branch_element": branch_elem,
            "score": score,
        })
    return wolun_list


# ─── 일운(日運) 계산 ─────────────────────────────────────────────
def calculate_ilun(target_date: date = None) -> dict:
    """일운 계산 — 특정 날짜의 일주"""
    if target_date is None:
        target_date = date.today()

    # 기준일: 1900년 1월 1일 = 甲子(갑자)일 (인덱스 0)
    base_date = date(1900, 1, 1)
    delta = (target_date - base_date).days
    stem_idx = (delta % 10)
    branch_idx = (delta % 12)
    stem = STEMS[stem_idx]
    branch = BRANCHES[branch_idx]

    lunar = solar_to_lunar(target_date.year, target_date.month, target_date.day)

    return {
        "date": target_date.isoformat(),
        "date_display": target_date.strftime("%B %d, %Y"),
        "stem": stem,
        "branch": branch,
        "stem_kr": STEM_KR.get(stem, stem),
        "branch_kr": BRANCH_KR.get(branch, branch),
        "branch_en": BRANCH_EN.get(branch, ""),
        "element": STEM_ELEMENT.get(stem, ""),
        "lunar": lunar,
    }


# ─── 길일(吉日) 계산 ─────────────────────────────────────────────
# 길일 기준: 일간이 사용자 일간과 상생(相生) 관계인 날
ELEMENT_GENERATES = {
    "목": "화",  # 목생화
    "화": "토",
    "토": "금",
    "금": "수",
    "수": "목",
}
ELEMENT_CONTROLS = {
    "목": "토",  # 목극토
    "화": "금",
    "토": "수",
    "금": "목",
    "수": "화",
}


def find_lucky_days(
    day_master_element: str,
    year: int = None, month: int = None,
    count: int = 10
) -> list[dict]:
    """해당 월에서 사용자 일간과 상생 관계인 길일 찾기"""
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    favorable_elements = {
        day_master_element,
        ELEMENT_GENERATES.get(day_master_element, ""),  # 내가 생하는 오행
    }
    # 나를 생해주는 오행 추가
    for elem, generated in ELEMENT_GENERATES.items():
        if generated == day_master_element:
            favorable_elements.add(elem)

    lucky_days = []
    start = date(year, month, 1)
    # 해당 월의 마지막 날
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    current = start
    while current <= end and len(lucky_days) < count:
        ilun = calculate_ilun(current)
        if ilun["element"] in favorable_elements:
            lucky_days.append({
                **ilun,
                "luck_level": "★★★" if ilun["element"] == day_master_element else "★★",
                "reason": f"{ELEMENT_EN.get(ilun['element'], '')} day harmonizes with your Day Master",
            })
        current += timedelta(days=1)

    return lucky_days


# ─── 궁합(宮合) 분석 ─────────────────────────────────────────────
def calculate_compatibility(chart_a: dict, chart_b: dict) -> dict:
    """두 사주 차트의 궁합 분석 (세분화된 5단계 점수)"""
    elem_a = chart_a["day_master"]["element"]
    elem_b = chart_b["day_master"]["element"]
    yin_yang_a = chart_a["day_master"].get("yin_yang", "")
    yin_yang_b = chart_b["day_master"].get("yin_yang", "")

    # 상생(相生) 관계 확인
    generates_a_to_b = ELEMENT_GENERATES.get(elem_a) == elem_b
    generates_b_to_a = ELEMENT_GENERATES.get(elem_b) == elem_a
    controls_a_to_b = ELEMENT_CONTROLS.get(elem_a) == elem_b
    controls_b_to_a = ELEMENT_CONTROLS.get(elem_b) == elem_a
    same_element = elem_a == elem_b

    # 음양 조합: 음+양 조합이 가장 이상적
    yin_yang_bonus = 5 if yin_yang_a != yin_yang_b else -3

    if generates_a_to_b or generates_b_to_a:
        base_score = 88
        relation = "Excellent (相生)"
        relation_km = "ល័អបំផុត"
        description = (
            f"{ELEMENT_EN[elem_a]} and {ELEMENT_EN[elem_b]} share a harmonious generating relationship. "
            f"You naturally support and uplift each other, creating a deeply nurturing bond."
        )
    elif same_element:
        # 동일 오행이라도 음양 차이에 따라 점수 차이
        base_score = 72 if yin_yang_a == yin_yang_b else 80
        relation = "Good (比和)" if yin_yang_a == yin_yang_b else "Very Good (比和)"
        relation_km = "ល័អ"
        description = (
            f"Both sharing {ELEMENT_EN[elem_a]} energy creates strong mutual understanding. "
            + ("Yin-Yang balance adds extra harmony to your bond." if yin_yang_a != yin_yang_b
               else "Similar energies may create competition — channel it into shared goals.")
        )
    elif controls_a_to_b or controls_b_to_a:
        # 상극이라도 어느 쪽이 극하는지에 따라 다름
        base_score = 42 if controls_a_to_b else 48  # 일방적 상극이 더 어려움
        relation = "Challenging (相尅)"
        relation_km = "ពិបាក"
        description = (
            f"The {ELEMENT_EN[elem_a]}–{ELEMENT_EN[elem_b]} dynamic creates tension but also passion. "
            f"Growth is possible with mutual respect and patience."
        )
    else:
        # 중립: 설기(\u6d29氣) 관계 — 나의 에너지를 소진시키는 관계
        base_score = 62
        relation = "Neutral (相洩)"
        relation_km = "ធ្ម្មតា"
        description = "Your energies are different but complementary. Balance and communication are key to a lasting relationship."

    # 음양 보정 적용
    base_score = max(30, min(100, base_score + yin_yang_bonus))

    # 오행 균형 점수 (두 차트 합산)
    combined_elements = {k: chart_a["five_elements"].get(k, 0) + chart_b["five_elements"].get(k, 0)
                         for k in ["\ubaa9", "\ud654", "\ud1a0", "\uae08", "\uc218"]}
    vals = list(combined_elements.values())
    balance_score = 100 - (max(vals) - min(vals)) * 4
    balance_score = max(0, min(100, balance_score))

    # 동물 조합 보정 (삼합/삼형 유사 로직)
    animal_a = chart_a.get("animal_sign", "")
    animal_b = chart_b.get("animal_sign", "")
    # 삼합 동물 그룹 (Rat-Dragon-Monkey, Ox-Snake-Rooster, Tiger-Horse-Dog, Rabbit-Goat-Pig)
    SANHAP = [
        {"Rat", "Dragon", "Monkey"},
        {"Ox", "Snake", "Rooster"},
        {"Tiger", "Horse", "Dog"},
        {"Rabbit", "Goat", "Pig"},
    ]
    animal_bonus = 0
    for group in SANHAP:
        if animal_a in group and animal_b in group:
            animal_bonus = 8
            break
    # 삼형 동물 (Rat-Horse, Ox-Goat, Tiger-Monkey, Rabbit-Rooster, Dragon-Dog, Snake-Pig)
    SANGHYEONG = [
        {"Rat", "Horse"}, {"Ox", "Goat"}, {"Tiger", "Monkey"},
        {"Rabbit", "Rooster"}, {"Dragon", "Dog"}, {"Snake", "Pig"}
    ]
    for pair in SANGHYEONG:
        if animal_a in pair and animal_b in pair:
            animal_bonus = -8
            break

    total_score = int(base_score * 0.6 + balance_score * 0.25 + (base_score + animal_bonus) * 0.15)
    total_score = max(30, min(97, total_score))

    # 각 영역별 점수 (일반 점수에서 다양하게 분산)
    love_score = max(30, min(100, total_score + (7 if yin_yang_a != yin_yang_b else -5)))
    marriage_score = max(30, min(100, total_score + animal_bonus - 2))
    business_score = max(30, min(100, total_score + (5 if same_element else -3)))
    friendship_score = max(30, min(100, total_score + 6))

    return {
        "score": total_score,
        "relation": relation,
        "relation_km": relation_km,
        "description": description,
        "element_a": {"element": elem_a, "en": ELEMENT_EN[elem_a], "icon": ELEMENT_ICON[elem_a]},
        "element_b": {"element": elem_b, "en": ELEMENT_EN[elem_b], "icon": ELEMENT_ICON[elem_b]},
        "combined_elements": combined_elements,
        "love_score": love_score,
        "marriage_score": marriage_score,
        "business_score": business_score,
        "friendship_score": friendship_score,
        "animal_bonus": animal_bonus,
        "advice": _compatibility_advice(elem_a, elem_b, total_score),
    }


def _compatibility_advice(elem_a: str, elem_b: str, score: int) -> list[str]:
    advice = []
    if score >= 80:
        advice.append("This is a highly compatible pairing — cherish and nurture this bond.")
        advice.append(f"Your {ELEMENT_EN[elem_a]} energy beautifully complements {ELEMENT_EN[elem_b]}.")
    elif score >= 65:
        advice.append("A good match with room for growth. Open communication strengthens your bond.")
        advice.append("Celebrate your differences as sources of learning.")
    else:
        advice.append("This pairing requires patience and mutual understanding.")
        advice.append("Focus on shared goals and respect each other's boundaries.")
    advice.append("In Cambodian tradition, consulting an elder or monk for auspicious wedding dates is recommended.")
    return advice


# ─── 초년/중년/말년 운 분석 ──────────────────────────────────────
def calculate_life_stages(chart: dict, birth_year: int) -> dict:
    """초년(0-30), 중년(31-60), 말년(61+) 운세 분석"""
    dominant = chart["dominant_element"]
    day_master = chart["day_master"]["element"]
    animal = chart["animal_sign"]

    # 오행 상생/상극 기반 인생 단계 분석
    early_elem = chart["pillars"]["year"]["element"]
    mid_elem = chart["pillars"]["month"]["element"]
    late_elem = chart["pillars"]["hour"]["element"]

    def stage_quality(elem: str, day_elem: str) -> tuple[str, int]:
        """5단계 점수: 상생/동일/설기/상극/피극"""
        # 나를 생해주는 오행 (상생, 가장 길함)
        generates_to_me = {v: k for k, v in ELEMENT_GENERATES.items()}
        if generates_to_me.get(day_elem) == elem:
            return "Excellent", 90
        # 내가 생해주는 오행 (설기, 소진되지만 나쁘지 않음)
        elif ELEMENT_GENERATES.get(day_elem) == elem:
            return "Favorable", 72
        elif elem == day_elem:
            return "Strong", 80
        # 나를 극하는 오행 (피극, 가장 흔함)
        elif ELEMENT_CONTROLS.get(elem) == day_elem:
            return "Difficult", 38
        # 내가 극하는 오행 (상극, 에너지 소모)
        elif ELEMENT_CONTROLS.get(day_elem) == elem:
            return "Challenging", 55
        else:
            return "Moderate", 65

    early_q, early_s = stage_quality(early_elem, day_master)
    mid_q, mid_s = stage_quality(mid_elem, day_master)
    late_q, late_s = stage_quality(late_elem, day_master)

    # 인생 단계별 품질 한국어 → 크메르어 매핑
    quality_km = {
        "Excellent": "ល័អបំផុត",
        "Strong": "ខ្លាងប្រើ",
        "Favorable": "ល័អ",
        "Moderate": "ធ្ម្មតា",
        "Challenging": "ពិបាក",
        "Difficult": "ពិបាកខ្លាង",
    }
    elem_km = {
        "목": "ឈើ",      # Wood
        "화": "ភ្លើង",   # Fire
        "토": "ដី",       # Earth
        "금": "លោហ",     # Metal
        "수": "ទឹក",     # Water
    }
    early_q_km = quality_km.get(early_q, early_q)
    mid_q_km = quality_km.get(mid_q, mid_q)
    late_q_km = quality_km.get(late_q, late_q)
    early_elem_km = elem_km.get(early_elem, ELEMENT_EN.get(early_elem, ''))
    mid_elem_km = elem_km.get(mid_elem, ELEMENT_EN.get(mid_elem, ''))
    late_elem_km = elem_km.get(late_elem, ELEMENT_EN.get(late_elem, ''))

    return {
        "early_life": {
            "period": "Ages 0–30 (Youth)",
            "period_km": "វ័យ ០-៣០ ឆ្នាំ",
            "quality": early_q,
            "quality_km": early_q_km,
            "score": early_s,
            "element": early_elem,
            "element_en": ELEMENT_EN.get(early_elem, ""),
            "element_km": early_elem_km,
            "description": f"Your early years are shaped by {ELEMENT_EN.get(early_elem, '')} energy. "
                           f"This period is {early_q.lower()} for your development.",
            "description_km": f"វ័យក្មេងរបស់អ្នកត្រូវបានកំណត់ដោយធាតុ {early_elem_km}។ "
                              f"រយៈពេលនេះ {early_q_km} សម្រាប់ការអភិវឌ្ឍន៍របស់អ្នក។",
        },
        "mid_life": {
            "period": "Ages 31–60 (Prime)",
            "period_km": "វ័យ ៣១-៦០ ឆ្នាំ",
            "quality": mid_q,
            "quality_km": mid_q_km,
            "score": mid_s,
            "element": mid_elem,
            "element_en": ELEMENT_EN.get(mid_elem, ""),
            "element_km": mid_elem_km,
            "description": f"Your prime years carry {ELEMENT_EN.get(mid_elem, '')} energy. "
                           f"Career and family life are {mid_q.lower()}.",
            "description_km": f"វ័យកណ្តាលរបស់អ្នកត្រូវបានកំណត់ដោយធាតុ {mid_elem_km}។ "
                              f"អាជីពនិងគ្រួសារមានស្ថានភាព {mid_q_km}។",
        },
        "late_life": {
            "period": "Ages 61+ (Wisdom)",
            "period_km": "វ័យ ៦១+ ឆ្នាំ",
            "quality": late_q,
            "quality_km": late_q_km,
            "score": late_s,
            "element": late_elem,
            "element_en": ELEMENT_EN.get(late_elem, ""),
            "element_km": late_elem_km,
            "description": f"Your later years are guided by {ELEMENT_EN.get(late_elem, '')} energy. "
                           f"This is a {late_q.lower()} period for wisdom and legacy.",
            "description_km": f"វ័យចំណាស់របស់អ្នកត្រូវបានណែនាំដោយធាតុ {late_elem_km}។ "
                              f"រយៈពេលនេះ {late_q_km} សម្រាប់ប្រាជ្ញា និងបុណ្យ។",
        },
    }
