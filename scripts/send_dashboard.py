#!/usr/bin/env python3
import os, sys, time, requests, pytz
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

DASHBOARD_URL    = os.environ.get("DASHBOARD_URL",    "https://ithcvopt-del.github.io/Production-Seng/")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
OVERRIDE_DATE    = os.environ.get("OVERRIDE_DATE",    "").strip()
TZ_ICT           = pytz.timezone("Asia/Bangkok")
SCREENSHOT_PATH  = Path("/tmp")

def get_report_date():
    if OVERRIDE_DATE:
        print(f"[DATE] Override: {OVERRIDE_DATE}")
        return OVERRIDE_DATE
    now = datetime.now(TZ_ICT)
    d   = now.date() if now.hour >= 8 else (now - timedelta(days=1)).date()
    s   = d.strftime("%d-%m-%Y")
    print(f"[DATE] ICT={now.strftime('%H:%M')} → report date={s}")
    return s

def capture(url, out_path):
    print(f"[CAPTURE] {url}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-dev-shm-usage","--disable-gpu"]
        )
        ctx  = browser.new_context(
            viewport={"width":1920,"height":1080},
            device_scale_factor=2,
            locale="th-TH",
            timezone_id="Asia/Bangkok"
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except PWTimeoutError:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(8000)
        page.add_style_tag(content="::-webkit-scrollbar{display:none!important}")
        page.screenshot(path=str(out_path), full_page=True, type="png")
        browser.close()
    print(f"[CAPTURE] Saved {out_path} ({out_path.stat().st_size/1024/1024:.1f} MB)")

def send(photo_path, report_date):
    now_str = datetime.now(TZ_ICT).strftime("%d/%m/%Y %H:%M")
    caption = (
        f"📊 *Production Dashboard*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 รายงานวันที่: *{report_date}*\n"
        f"🕐 ส่งเมื่อ: `{now_str} ICT`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 [ดู Dashboard]({DASHBOARD_URL})"
    )
    size_mb = photo_path.stat().st_size / 1024 / 1024
    method  = "sendPhoto" if size_mb <= 10 else "sendDocument"
    field   = "photo"     if size_mb <= 10 else "document"
    print(f"[TELEGRAM] Sending via {method} ({size_mb:.1f} MB)")

    with open(photo_path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            data={"chat_id": TELEGRAM_CHAT_ID,
                  "caption": caption, "parse_mode": "Markdown"},
            files={field: ("dashboard.png", f, "image/png")},
            timeout=60
        )
    if r.status_code == 200:
        print(f"[TELEGRAM] ✅ Sent! message_id={r.json()['result']['message_id']}")
    else:
        print(f"[TELEGRAM] ❌ {r.status_code}: {r.text}")
        sys.exit(1)

def main():
    if not TELEGRAM_TOKEN:
        print("[ERROR] TELEGRAM_TOKEN not set"); sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        print("[ERROR] TELEGRAM_CHAT_ID not set"); sys.exit(1)

    report_date = get_report_date()
    out_path    = SCREENSHOT_PATH / f"dashboard_{report_date.replace('-','')}.png"

    for attempt in range(1, 4):
        try:
            capture(DASHBOARD_URL, out_path)
            break
        except Exception as e:
            print(f"[CAPTURE] Attempt {attempt}/3 failed: {e}")
            if attempt == 3: sys.exit(1)
            time.sleep(5)

    send(out_path, report_date)
    print("[DONE] ✅")

if __name__ == "__main__":
    main()
