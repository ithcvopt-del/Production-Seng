#!/usr/bin/env python3
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

DASHBOARD_URL = "https://ithcvopt-del.github.io/Production-Seng/"
SCREENSHOT_PATH = "/tmp/dashboard.png"
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TH_TZ = timezone(timedelta(hours=7))
now_th = datetime.now(TH_TZ)

def get_graph_date(current_time):
    if current_time.hour <= 7:
        graph_date = current_time.date() - timedelta(days=1)
    else:
        graph_date = current_time.date()
    return graph_date.strftime("%d-%m-%Y")

graph_date_str = get_graph_date(now_th)
now_str = now_th.strftime("%d/%m/%Y %H:%M")

def screenshot():
    print(f"กำลังถ่าย screenshot จาก {DASHBOARD_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
        page = browser.new_page(
            viewport={"width": 1920, "height": 1200},
            device_scale_factor=2,
        )
        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(3_000)
        page.screenshot(path=SCREENSHOT_PATH, full_page=True)
        browser.close()
    print(f"screenshot บันทึกที่ {SCREENSHOT_PATH}")

def send():
    print("กำลังส่งรูปไปยัง Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    caption = (
        f"📊 *Production Dashboard*\n"
        f"📅 กราฟวันที่: {graph_date_str}\n"
        f"🕐 อัปเดต: {now_str} (ICT)"
    )
    with open(SCREENSHOT_PATH, "rb") as photo:
        resp = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("dashboard.png", photo, "image/png")},
            timeout=30,
        )
    if resp.status_code == 200:
        print(f"ส่งสำเร็จ! (กราฟวันที่ {graph_date_str})")
    else:
        print(f"Telegram API error: {resp.status_code} - {resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    screenshot()
    send()
