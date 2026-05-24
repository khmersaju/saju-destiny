"""
매일 아침 7시 (프놈펜 UTC+7) 회원들에게 오늘의 운세 푸시 알림 발송
실행: python3.11 push_scheduler.py
"""
import asyncio
import sqlite3
import json
import time
from datetime import datetime, timezone, timedelta
import sys, os

sys.path.insert(0, os.path.dirname(__file__))

PHNOM_PENH_TZ = timezone(timedelta(hours=7))
DB_PATH = os.path.join(os.path.dirname(__file__), 'saju_destiny.db')

def get_today_info():
    """오늘의 일주 정보 가져오기"""
    try:
        from app.services.saju_engine_v2 import calculate_ilun, solar_to_lunar
        now = datetime.now(PHNOM_PENH_TZ)
        ilun = calculate_ilun(now.year, now.month, now.day)
        lunar = solar_to_lunar(now.year, now.month, now.day)
        return {
            'day_pillar': f"{ilun.get('stem','')}{ilun.get('branch','')}",
            'animal': ilun.get('animal', ''),
            'element': ilun.get('element', ''),
            'date': now.strftime('%Y-%m-%d'),
        }
    except Exception as e:
        print(f"[Scheduler] Error getting today info: {e}")
        return {'day_pillar': '—', 'animal': '', 'date': datetime.now().strftime('%Y-%m-%d')}

def get_push_subscribers():
    """푸시 알림 동의한 회원 목록"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, email, full_name, khmer_name, language_pref, push_token
            FROM users
            WHERE push_token IS NOT NULL AND push_token != ''
            AND is_active = 1
        """)
        rows = c.fetchall()
        conn.close()
        return [{'id': r[0], 'email': r[1], 'full_name': r[2], 'khmer_name': r[3],
                 'lang': r[4] or 'km', 'push_token': r[5]} for r in rows]
    except Exception as e:
        print(f"[Scheduler] DB error: {e}")
        return []

def build_notification(user, today_info):
    """사용자별 알림 메시지 생성"""
    lang = user.get('lang', 'km')
    name = user.get('khmer_name') or user.get('full_name') or ''
    pillar = today_info.get('day_pillar', '—')
    animal = today_info.get('animal', '')
    date_str = today_info.get('date', '')

    if lang == 'km':
        greeting = f"🌅 សុប្រភព{', ' + name if name else ''}!"
        body = f"សសរស្ដម្ភថ្ងៃ: {pillar} · {animal}\nចុចដើម្បីអានជោគជតាប្រចាំថ្ងៃ"
    else:
        greeting = f"🌅 Good morning{', ' + name if name else ''}!"
        body = f"Today's Pillar: {pillar} · {animal}\nTap to read your daily fortune"

    return {
        'title': greeting,
        'body': body,
        'icon': '/icon-192.png',
        'tag': f'daily-{date_str}',
        'data': {'url': '/?mode=daily', 'date': date_str}
    }

def log_notification_sent(user_id, date_str, status):
    """알림 발송 기록 저장"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS push_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                sent_date TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("INSERT INTO push_log (user_id, sent_date, status) VALUES (?,?,?)",
                  (user_id, date_str, status))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Scheduler] Log error: {e}")

def already_sent_today(user_id, date_str):
    """오늘 이미 발송했는지 확인"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM push_log WHERE user_id=? AND sent_date=? AND status='sent'",
                  (user_id, date_str))
        result = c.fetchone()
        conn.close()
        return result is not None
    except:
        return False

async def send_daily_notifications():
    """매일 아침 7시 알림 발송 메인 함수"""
    now_pp = datetime.now(PHNOM_PENH_TZ)
    print(f"[Scheduler] Running at {now_pp.strftime('%Y-%m-%d %H:%M')} (Phnom Penh)")

    today_info = get_today_info()
    subscribers = get_push_subscribers()
    date_str = today_info['date']

    print(f"[Scheduler] Today: {today_info['day_pillar']} · {today_info['animal']}")
    print(f"[Scheduler] Subscribers with push: {len(subscribers)}")

    sent_count = 0
    for user in subscribers:
        if already_sent_today(user['id'], date_str):
            continue
        notification = build_notification(user, today_info)
        # 실제 Web Push 발송은 pywebpush 라이브러리 필요
        # 현재는 로그만 기록 (VAPID 키 설정 후 활성화)
        print(f"[Scheduler] → {user['email']}: {notification['title']}")
        log_notification_sent(user['id'], date_str, 'sent')
        sent_count += 1
        await asyncio.sleep(0.05)  # 과부하 방지

    print(f"[Scheduler] Done. Sent: {sent_count}/{len(subscribers)}")
    return sent_count

async def scheduler_loop():
    """스케줄러 루프 - 매 분마다 7시인지 확인"""
    print("[Scheduler] Started. Waiting for 07:00 Phnom Penh time...")
    last_run_date = None

    while True:
        now_pp = datetime.now(PHNOM_PENH_TZ)
        today_str = now_pp.strftime('%Y-%m-%d')

        # 매일 오전 7:00~7:05 사이에 한 번만 실행
        if now_pp.hour == 7 and now_pp.minute < 5 and last_run_date != today_str:
            print(f"[Scheduler] 🌅 Morning trigger! {today_str}")
            await send_daily_notifications()
            last_run_date = today_str

        await asyncio.sleep(60)  # 1분마다 체크

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='즉시 테스트 발송')
    args = parser.parse_args()

    if args.test:
        print("[Scheduler] Test mode - sending now...")
        asyncio.run(send_daily_notifications())
    else:
        asyncio.run(scheduler_loop())
