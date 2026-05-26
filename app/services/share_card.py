"""
Saju Destiny — SNS 공유 카드 이미지 생성 모듈
1080×1080 정사각형 카드 (Instagram/Facebook 최적화)
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import qrcode
import io
import os
import math

# ─── 폰트 경로 ────────────────────────────────────────────────────
FONT_DIR = "/usr/share/fonts/truetype/noto"
FONT_KH_BOLD   = os.path.join(FONT_DIR, "NotoSansKhmer-Bold.ttf")
FONT_KH_REG    = os.path.join(FONT_DIR, "NotoSansKhmer-Regular.ttf")
FONT_KH_MEDIUM = os.path.join(FONT_DIR, "NotoSansKhmer-Medium.ttf")
FONT_EN_BOLD   = os.path.join(FONT_DIR, "NotoSans-Bold.ttf")
FONT_EN_REG    = os.path.join(FONT_DIR, "NotoSans-Regular.ttf")
FONT_EN_MEDIUM = os.path.join(FONT_DIR, "NotoSans-Medium.ttf")
FONT_CJK       = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

# 폰트 fallback 처리
def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# ─── 색상 팔레트 ──────────────────────────────────────────────────
COLORS = {
    "bg_dark":    (1, 9, 43),        # #01092B 딥 네이비
    "bg_card":    (8, 20, 65),        # #081441 카드 배경
    "gold":       (212, 175, 55),     # #D4AF37 골드
    "gold_light": (255, 215, 80),     # #FFD750 밝은 골드
    "white":      (255, 255, 255),
    "white_70":   (255, 255, 255, 178),
    "white_40":   (255, 255, 255, 102),
    "accent":     (100, 160, 255),    # 밝은 블루 액센트
    # 오행 색상
    "wood":  (72, 199, 116),   # 초록
    "fire":  (232, 64, 64),    # 빨강
    "earth": (212, 160, 23),   # 황토
    "metal": (180, 180, 200),  # 은빛
    "water": (74, 144, 217),   # 파랑
}

ELEMENT_COLORS = {
    "목": COLORS["wood"],
    "화": COLORS["fire"],
    "토": COLORS["earth"],
    "금": COLORS["metal"],
    "수": COLORS["water"],
}

ELEMENT_EN = {"목": "Wood", "화": "Fire", "토": "Earth", "금": "Metal", "수": "Water"}
ELEMENT_KM = {"목": "ឈើ", "화": "ភ្លើង", "토": "ដី", "금": "លោហ", "수": "ទឹក"}
ELEMENT_ICON = {"목": "🌿", "화": "🔥", "토": "🌍", "금": "⚙️", "수": "💧"}

STEM_EN = {
    "甲": "Yang Wood", "乙": "Yin Wood",
    "丙": "Yang Fire", "丁": "Yin Fire",
    "戊": "Yang Earth", "己": "Yin Earth",
    "庚": "Yang Metal", "辛": "Yin Metal",
    "壬": "Yang Water", "癸": "Yin Water",
}
BRANCH_EN = {
    "子": "Rat", "丑": "Ox", "寅": "Tiger", "卯": "Rabbit",
    "辰": "Dragon", "巳": "Snake", "午": "Horse", "未": "Goat",
    "申": "Monkey", "酉": "Rooster", "戌": "Dog", "亥": "Pig",
}
STEM_ELEMENT = {
    "甲": "목", "乙": "목", "丙": "화", "丁": "화",
    "戊": "토", "己": "토", "庚": "금", "辛": "금",
    "壬": "수", "癸": "수",
}

def _draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """둥근 모서리 사각형 그리기"""
    x0, y0, x1, y1 = xy
    r = radius
    if fill:
        draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
        draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
        draw.ellipse([x0, y0, x0 + 2*r, y0 + 2*r], fill=fill)
        draw.ellipse([x1 - 2*r, y0, x1, y0 + 2*r], fill=fill)
        draw.ellipse([x0, y1 - 2*r, x0 + 2*r, y1], fill=fill)
        draw.ellipse([x1 - 2*r, y1 - 2*r, x1, y1], fill=fill)
    if outline:
        draw.arc([x0, y0, x0 + 2*r, y0 + 2*r], 180, 270, fill=outline, width=width)
        draw.arc([x1 - 2*r, y0, x1, y0 + 2*r], 270, 360, fill=outline, width=width)
        draw.arc([x0, y1 - 2*r, x0 + 2*r, y1], 90, 180, fill=outline, width=width)
        draw.arc([x1 - 2*r, y1 - 2*r, x1, y1], 0, 90, fill=outline, width=width)
        draw.line([x0 + r, y0, x1 - r, y0], fill=outline, width=width)
        draw.line([x0 + r, y1, x1 - r, y1], fill=outline, width=width)
        draw.line([x0, y0 + r, x0, y1 - r], fill=outline, width=width)
        draw.line([x1, y0 + r, x1, y1 - r], fill=outline, width=width)

def _draw_stars(draw, cx, cy, count, radius, color, size=3):
    """별 장식 그리기"""
    for i in range(count):
        angle = (2 * math.pi / count) * i
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        draw.ellipse([x - size, y - size, x + size, y + size], fill=color)

def _make_qr(url: str, size: int = 120) -> Image.Image:
    """QR 코드 생성 (투명 배경)"""
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=(212, 175, 55), back_color=(8, 20, 65))
    return img.resize((size, size), Image.LANCZOS)

def _draw_element_bar(draw, x, y, w, h, value, max_val, color, label_font, label_km, label_en, count):
    """오행 막대 그래프 한 줄"""
    # 배경 바
    _draw_rounded_rect(draw, [x, y, x + w, y + h], radius=h//2,
                       fill=(255, 255, 255, 20))
    # 채워진 바
    fill_w = max(h, int(w * (value / max(max_val, 1))))
    if fill_w > h:
        _draw_rounded_rect(draw, [x, y, x + fill_w, y + h], radius=h//2, fill=color)
    # 라벨 (크메르어)
    draw.text((x - 10, y + h//2), label_km, font=label_font, fill=COLORS["white"], anchor="rm")
    # 숫자
    count_font = _load_font(FONT_EN_BOLD, 22)
    draw.text((x + w + 12, y + h//2), str(count), font=count_font, fill=color, anchor="lm")

def generate_share_card(
    name: str,
    birth_info: str,          # "1981.5.23 | Male"
    pillars: dict,            # chart["pillars"]
    five_elements: dict,      # {"목":1, "화":1, "토":2, "금":3, "수":1}
    day_master: dict,         # chart["day_master"]
    animal_sign: str,         # "Rooster"
    animal_sign_km: str,      # "មាន់"
    dominant_element: str,    # "금"
    app_url: str = "https://web-production-d0bd4.up.railway.app",
    lang: str = "en",
) -> bytes:
    """
    1080×1350 세로형 공유 카드 이미지 생성 (Instagram Story / Facebook 최적화)
    Returns: PNG bytes
    """
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img, "RGBA")

    # ── 배경 별빛 효과 ────────────────────────────────────────────
    import random
    rng = random.Random(42)
    for _ in range(120):
        sx = rng.randint(0, W)
        sy = rng.randint(0, H)
        ss = rng.randint(1, 3)
        alpha = rng.randint(60, 180)
        draw.ellipse([sx, sy, sx + ss, sy + ss], fill=(255, 255, 255, alpha))

    # ── 상단 그라데이션 원형 글로우 ───────────────────────────────
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(300, 0, -10):
        alpha = int(40 * (1 - r / 300))
        gd.ellipse([W//2 - r, -r//2, W//2 + r, r + r//2],
                   fill=(*COLORS["gold"], alpha))
    img.paste(glow, (0, 0), glow)

    # ── 폰트 로드 ─────────────────────────────────────────────────
    f_title_lg = _load_font(FONT_EN_BOLD, 52)
    f_title_sm = _load_font(FONT_EN_BOLD, 28)
    f_sub      = _load_font(FONT_EN_REG, 22)
    f_km_lg    = _load_font(FONT_KH_BOLD, 38)
    f_km_md    = _load_font(FONT_KH_MEDIUM, 26)
    f_km_sm    = _load_font(FONT_KH_REG, 20)
    f_cjk_xl   = _load_font(FONT_CJK, 72)
    f_cjk_lg   = _load_font(FONT_CJK, 48)
    f_cjk_md   = _load_font(FONT_CJK, 32)
    f_en_sm    = _load_font(FONT_EN_REG, 18)
    f_en_xs    = _load_font(FONT_EN_REG, 15)
    f_en_bold_md = _load_font(FONT_EN_BOLD, 22)
    f_en_bold_sm = _load_font(FONT_EN_BOLD, 18)

    # ══════════════════════════════════════════════════════════════
    # 섹션 1: 앱 브랜드 헤더 (상단)
    # ══════════════════════════════════════════════════════════════
    y = 48

    # 골드 장식선
    draw.line([(W//2 - 160, y + 18), (W//2 - 40, y + 18)], fill=COLORS["gold"], width=2)
    draw.line([(W//2 + 40, y + 18), (W//2 + 160, y + 18)], fill=COLORS["gold"], width=2)
    draw.ellipse([W//2 - 6, y + 12, W//2 + 6, y + 24], fill=COLORS["gold"])

    # 앱 이름
    draw.text((W//2, y + 48), "Saju Destiny", font=f_title_lg,
              fill=COLORS["gold_light"], anchor="mm")
    draw.text((W//2, y + 96), "ជោគជតា", font=f_km_lg,
              fill=COLORS["white"], anchor="mm")
    draw.text((W//2, y + 136), "Traditional Four Pillars Fortune", font=f_sub,
              fill=(180, 200, 255), anchor="mm")

    # ══════════════════════════════════════════════════════════════
    # 섹션 2: 사용자 정보 배지
    # ══════════════════════════════════════════════════════════════
    y = 230
    badge_x, badge_w, badge_h = 60, W - 120, 80
    _draw_rounded_rect(draw, [badge_x, y, badge_x + badge_w, y + badge_h],
                       radius=16, fill=(255, 255, 255, 15))
    _draw_rounded_rect(draw, [badge_x, y, badge_x + badge_w, y + badge_h],
                       radius=16, outline=COLORS["gold"], width=1)

    draw.text((W//2, y + 22), name, font=f_title_sm,
              fill=COLORS["gold_light"], anchor="mm")
    draw.text((W//2, y + 56), birth_info, font=f_en_sm,
              fill=(180, 200, 255), anchor="mm")

    # ══════════════════════════════════════════════════════════════
    # 섹션 3: 사주 4기둥 차트 (핵심 시각 요소)
    # ══════════════════════════════════════════════════════════════
    y = 340
    col_labels = ["YEAR", "MONTH", "DAY", "HOUR"]
    col_keys   = ["year", "month", "day", "hour"]
    col_w = (W - 120) // 4
    col_start = 60

    # 섹션 타이틀
    draw.text((W//2, y), "✦  SAJU CHART  ✦", font=f_en_bold_md,
              fill=COLORS["gold"], anchor="mm")
    y += 36

    for i, key in enumerate(col_keys):
        p = pillars.get(key, {})
        stem   = p.get("stem", "?")
        branch = p.get("branch", "?")
        elem   = p.get("element", "목")
        elem_color = ELEMENT_COLORS.get(elem, COLORS["white"])
        cx = col_start + col_w * i + col_w // 2

        # 기둥 배경 카드
        card_x = col_start + col_w * i + 8
        card_w = col_w - 16
        _draw_rounded_rect(draw, [card_x, y, card_x + card_w, y + 220],
                           radius=14, fill=(255, 255, 255, 12))
        _draw_rounded_rect(draw, [card_x, y, card_x + card_w, y + 220],
                           radius=14, outline=(*elem_color, 120), width=2)

        # 기둥 라벨 (YEAR/MONTH/DAY/HOUR)
        draw.text((cx, y + 18), col_labels[i], font=f_en_xs,
                  fill=elem_color, anchor="mm")

        # 천간 (큰 한자)
        draw.text((cx, y + 80), stem, font=f_cjk_xl,
                  fill=COLORS["white"], anchor="mm")

        # 지지 (중간 한자)
        draw.text((cx, y + 148), branch, font=f_cjk_lg,
                  fill=COLORS["white"], anchor="mm")

        # 오행 레이블
        elem_en = ELEMENT_EN.get(elem, "")
        draw.text((cx, y + 200), elem_en, font=f_en_xs,
                  fill=elem_color, anchor="mm")

    y += 248

    # Day Master 정보
    dm_elem = day_master.get("element", "목")
    dm_stem = day_master.get("stem", "")
    dm_en   = STEM_EN.get(dm_stem, "")
    dm_color = ELEMENT_COLORS.get(dm_elem, COLORS["white"])

    draw.text((W//2, y),
              f"Day Master: {dm_en}  ·  Year of {animal_sign}",
              font=f_en_sm, fill=(180, 200, 255), anchor="mm")

    # ══════════════════════════════════════════════════════════════
    # 섹션 4: 오행 분포 바 차트
    # ══════════════════════════════════════════════════════════════
    y += 44
    draw.text((W//2, y), "✦  FIVE ELEMENTS  ✦", font=f_en_bold_md,
              fill=COLORS["gold"], anchor="mm")
    y += 34

    elem_order = ["목", "화", "토", "금", "수"]
    max_val = max(five_elements.values()) if five_elements else 1
    bar_x = 160
    bar_w = W - bar_x - 80
    bar_h = 22
    bar_gap = 34

    for elem_key in elem_order:
        count = five_elements.get(elem_key, 0)
        color = ELEMENT_COLORS[elem_key]
        km_label = ELEMENT_KM[elem_key]
        en_label = ELEMENT_EN[elem_key]

        # 크메르어 라벨
        draw.text((bar_x - 12, y + bar_h // 2), km_label,
                  font=f_km_sm, fill=COLORS["white"], anchor="rm")

        # 배경 바
        _draw_rounded_rect(draw, [bar_x, y, bar_x + bar_w, y + bar_h],
                           radius=bar_h // 2, fill=(255, 255, 255, 18))

        # 채워진 바
        fill_w = max(bar_h, int(bar_w * (count / max(max_val, 1))))
        _draw_rounded_rect(draw, [bar_x, y, bar_x + fill_w, y + bar_h],
                           radius=bar_h // 2, fill=(*color, 220))

        # 카운트
        draw.text((bar_x + bar_w + 14, y + bar_h // 2), str(count),
                  font=f_en_bold_md, fill=color, anchor="lm")

        y += bar_gap

    # ══════════════════════════════════════════════════════════════
    # 섹션 5: 지배 오행 하이라이트
    # ══════════════════════════════════════════════════════════════
    y += 10
    dom_color = ELEMENT_COLORS.get(dominant_element, COLORS["gold"])
    dom_en    = ELEMENT_EN.get(dominant_element, "")
    dom_km    = ELEMENT_KM.get(dominant_element, "")

    _draw_rounded_rect(draw, [60, y, W - 60, y + 72], radius=16,
                       fill=(*dom_color, 30))
    _draw_rounded_rect(draw, [60, y, W - 60, y + 72], radius=16,
                       outline=(*dom_color, 180), width=2)

    draw.text((W//2, y + 20), f"Dominant Element", font=f_en_xs,
              fill=(200, 220, 255), anchor="mm")
    draw.text((W//2, y + 50),
              f"{dom_en}  ·  {dom_km}",
              font=f_en_bold_md, fill=dom_color, anchor="mm")

    # ══════════════════════════════════════════════════════════════
    # 섹션 6: CTA 문구 + QR 코드 (하단)
    # ══════════════════════════════════════════════════════════════
    y += 96

    # 구분선
    draw.line([(60, y), (W - 60, y)], fill=(*COLORS["gold"], 80), width=1)
    y += 24

    # CTA 문구 (크메르어 + 영어)
    cta_km = "ចង់ដឹងជោគជតារបស់អ្នកដែរទេ?"
    cta_en = "✨ Curious about your destiny? ✨"
    cta_sub = "Scan QR · Free · No ads"
    cta_app = "▶  Try Saju Destiny Now  ◀"

    # CTA 배경 박스
    _draw_rounded_rect(draw, [60, y, W - 60, y + 64],
                       radius=14, fill=(212, 175, 55, 25))
    draw.text((W//2, y + 14), cta_km, font=f_km_md,
              fill=COLORS["gold_light"], anchor="mm")
    draw.text((W//2, y + 48), cta_en, font=f_en_bold_md,
              fill=COLORS["white"], anchor="mm")

    # QR 코드
    qr_size = 130
    qr_img = _make_qr(app_url, size=qr_size)
    qr_x = W // 2 - qr_size // 2
    qr_y = y + 72

    # QR 배경
    _draw_rounded_rect(draw, [qr_x - 10, qr_y - 10,
                               qr_x + qr_size + 10, qr_y + qr_size + 10],
                       radius=12, fill=COLORS["bg_card"])
    img.paste(qr_img, (qr_x, qr_y))

    y = qr_y + qr_size + 16
    draw.text((W//2, y + 8), cta_sub, font=f_en_xs,
              fill=(160, 180, 220), anchor="mm")
    # CTA 버튼 스타일
    btn_y = y + 28
    _draw_rounded_rect(draw, [W//2 - 220, btn_y, W//2 + 220, btn_y + 44],
                       radius=22, fill=COLORS["gold"])
    draw.text((W//2, btn_y + 22), cta_app, font=f_en_bold_md,
              fill=COLORS["bg_dark"], anchor="mm")

    # 하단 골드 장식선
    y += 56
    draw.line([(W//2 - 160, y), (W//2 - 40, y)], fill=COLORS["gold"], width=2)
    draw.line([(W//2 + 40, y), (W//2 + 160, y)], fill=COLORS["gold"], width=2)
    draw.ellipse([W//2 - 5, y - 5, W//2 + 5, y + 5], fill=COLORS["gold"])

    # ── PNG bytes 반환 ────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


# ─── 테스트 실행 ──────────────────────────────────────────────────
if __name__ == "__main__":
    sample_pillars = {
        "year":  {"stem": "辛", "branch": "酉", "element": "금"},
        "month": {"stem": "癸", "branch": "巳", "element": "수"},
        "day":   {"stem": "辛", "branch": "丑", "element": "금"},
        "hour":  {"stem": "乙", "branch": "未", "element": "목"},
    }
    sample_elements = {"목": 1, "화": 1, "토": 2, "금": 3, "수": 1}
    sample_dm = {"stem": "辛", "element": "금", "yin_yang": "음"}

    data = generate_share_card(
        name="Ly Samnang",
        birth_info="1981.5.23  |  Male",
        pillars=sample_pillars,
        five_elements=sample_elements,
        day_master=sample_dm,
        animal_sign="Rooster",
        animal_sign_km="មាន់",
        dominant_element="금",
        app_url="https://web-production-d0bd4.up.railway.app",
    )
    with open("/tmp/share_card_test.png", "wb") as f:
        f.write(data)
    print(f"생성 완료: {len(data)//1024}KB → /tmp/share_card_test.png")
