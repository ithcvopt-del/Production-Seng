#!/usr/bin/env python3
"""
Dashboard Screenshot Sender to Telegram
Runs once per execution — triggered by GitHub Actions cron schedule.
"""

import asyncio
import os
import logging
import requests
from datetime import datetime, timedelta
import pytz
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────
# CONFIG — อ่านจาก Environment Variables (GitHub Secrets)
# ─────────────────────────────────────────────
DASHBOARD_URL    = "https://ithcvopt-del.github.io/Production-Seng/"
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TIMEZONE         = pytz.timezone("Asia/Bangkok")
SCREENSHOT_PATH  = "/tmp/dashboard_screenshot.png"

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HELPER: resolve "report date"
# ─────────────────────────────────────────────
def get_report_date(now: datetime):
    """
    08:06 – 23:59  → report date = today
    00:00 – 07:59  → report date = yesterday
    """
    if now.hour < 8 or (now.hour == 8 and now.minute < 6):
        return (now - timedelta(days=1)).date()
    return now.date()


# ─────────────────────────────────────────────
# CAPTURE SCREENSHOT
# ─────────────────────────────────────────────
async def capture_dashboard() -> str:
    log.info("Launching browser …")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,   # high-DPI
        )
        page = await context.new_page()

        log.info(f"Opening {DASHBOARD_URL}")
        await page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(6_000)   # รอกราฟ render เสร็จ

        await page.screenshot(path=SCREENSHOT_PATH, full_page=True, type="png")
        await browser.close()

    log.info(f"Screenshot saved → {SCREENSHOT_PATH}")
    return SCREENSHOT_PATH


# ─────────────────────────────────────────────
# SEND TO TELEGRAM
# ─────────────────────────────────────────────
def send_to_telegram(image_path: str, report_date, send_time: datetime):
    caption = (
        f"📊 *Production Dashboard*\n"
        f"📅 วันที่รายงาน: *{report_date.strftime('%d-%m-%Y')}*\n"
        f"🕐 ส่งเมื่อ: {send_time.strftime('%d/%m/%Y %H:%M')} (ICT)"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

    with open(image_path, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
            },
            files={"photo": ("dashboard.png", photo, "image/png")},
            timeout=60,
        )

    if response.status_code == 200:
        log.info("✅ Sent to Telegram successfully.")
    else:
        log.error(f"❌ Telegram error {response.status_code}: {response.text}")
        response.raise_for_status()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
async def main():
    now = datetime.now(TIMEZONE)
    report_date = get_report_date(now)
    log.info(f"⏰ Running at {now.strftime('%Y-%m-%d %H:%M:%S')} ICT | Report date: {report_date}")

    path = await capture_dashboard()
    send_to_telegram(path, report_date, now)


if __name__ == "__main__":
    asyncio.run(main())
