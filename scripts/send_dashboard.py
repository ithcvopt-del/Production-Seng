#!/usr/bin/env python3
"""
send_dashboard.py
─────────────────
Capture a high-resolution screenshot of the Production dashboard
and send it to a Telegram group every hour.

Date logic (ICT = GMT+7):
  • 08:06 ICT on day D  →  07:06 ICT on day D+1  : send graph for day D
  • 07:06 ICT on day D  →  (i.e. hour < 8)        : send graph for day D-1
"""

import os
import sys
import time
import requests
import pytz
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
DASHBOARD_URL   = os.environ.get("DASHBOARD_URL",   "https://ithcvopt-del.github.io/Production-Seng/")
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN",  "")
TELEGRAM_CHAT_ID= os.environ.get("TELEGRAM_CHAT_ID","")
OVERRIDE_DATE   = os.environ.get("OVERRIDE_DATE",   "").strip()   # DD-MM-YYYY

TZ_ICT = pytz.timezone("Asia/Bangkok")   # ICT = GMT+7 (ใช้ได้กับลาว)

SCREENSHOT_PATH = Path("/tmp/dashboard_{date}.png")
VIEWPORT_W      = 1920
VIEWPORT_H      = 1080
DEVICE_SCALE    = 2          # retina → ภาพ 3840×2160 จริง
PAGE_WAIT_MS    = 8000       # รอให้กราฟ render ครบ (ms)
MAX_RETRIES     = 3


# ═══════════════════════════════════════════════════════════════════
# DATE LOGIC
# ═══════════════════════════════════════════════════════════════════
def get_report_date() -> str:
    """
    คืนค่าวันที่รายงาน (DD-MM-YYYY ตาม ICT)
    - ถ้า override_date มีค่า → ใช้ค่านั้น
    - ถ้า ICT hour >= 8 → วันนี้
    - ถ้า ICT hour < 8  → เมื่อวาน
    """
    if OVERRIDE_DATE:
        print(f"[DATE] Using override date: {OVERRIDE_DATE}")
        return OVERRIDE_DATE

    now_ict = datetime.now(TZ_ICT)
    if now_ict.hour >= 8:
        report_date = now_ict.date()
    else:
        report_date = (now_ict - timedelta(days=1)).date()

    date_str = report_date.strftime("%d-%m-%Y")
    print(f"[DATE] ICT now={now_ict.strftime('%Y-%m-%d %H:%M')} → report date={date_str}")
    return date_str


def get_send_time_str() -> str:
    """คืนสตริงเวลา ICT ตอนนี้ สำหรับ caption"""
    return datetime.now(TZ_ICT).strftime("%d/%m/%Y %H:%M")


# ═══════════════════════════════════════════════════════════════════
# SCREENSHOT
# ═══════════════════════════════════════════════════════════════════
def capture_screenshot(url: str, out_path: Path) -> Path:
    """ถ่าย screenshot ด้วย Playwright แบบ high-resolution"""
    print(f"[CAPTURE] Opening {url}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--force-device-scale-factor=2",
            ],
        )
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=DEVICE_SCALE,
            locale="th-TH",
            timezone_id="Asia/Bangkok",
        )
        page = context.new_page()

        # ─── Load page ───────────────────────────────────────────
        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
        except PWTimeoutError:
            print("[CAPTURE] networkidle timeout – continuing anyway")
            page.goto(url, wait_until="domcontentloaded", timeout=20_000)

        # ─── รอให้ chart / graph render ────────────────────────────
        print(f"[CAPTURE] Waiting {PAGE_WAIT_MS} ms for charts to render …")
        page.wait_for_timeout(PAGE_WAIT_MS)

        # ─── ซ่อน scrollbar ────────────────────────────────────────
        page.add_style_tag(content="""
            ::-webkit-scrollbar { display: none !important; }
            * { scrollbar-width: none !important; }
        """)

        # ─── Screenshot ────────────────────────────────────────────
        page.screenshot(
            path=str(out_path),
            full_page=True,
            type="png",
        )
        browser.close()

    # ─── Post-process: เพิ่ม sharpness (optional) ─────────────────
    try:
        img = Image.open(out_path)
        print(f"[CAPTURE] Screenshot size: {img.size[0]}×{img.size[1]} px")
        img.save(out_path, format="PNG", optimize=False, compress_level=1)
    except Exception as e:
        print(f"[CAPTURE] PIL post-process warning: {e}")

    print(f"[CAPTURE] Saved → {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════════
def build_caption(report_date: str, send_time: str) -> str:
    """สร้าง caption สำหรับภาพ"""
    return (
        f"📊 *Production Dashboard*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 รายงานวันที่: *{report_date}*\n"
        f"🕐 ส่งเมื่อ: `{send_time} ICT`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 [ดู Dashboard เต็ม]({DASHBOARD_URL})"
    )


def send_photo_to_telegram(photo_path: Path, caption: str) -> bool:
    """ส่งรูปภาพพร้อม caption ไปยัง Telegram"""
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] ERROR: TELEGRAM_TOKEN is not set")
        return False
    if not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] ERROR: TELEGRAM_CHAT_ID is not set")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    file_size_mb = photo_path.stat().st_size / 1024 / 1024
    print(f"[TELEGRAM] Sending photo ({file_size_mb:.1f} MB) to chat {TELEGRAM_CHAT_ID} …")

    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
                "disable_notification": False,
            },
            files={"photo": ("dashboard.png", f, "image/png")},
            timeout=60,
        )

    if resp.status_code == 200:
        msg_id = resp.json().get("result", {}).get("message_id", "?")
        print(f"[TELEGRAM] ✅ Sent! message_id={msg_id}")
        return True
    else:
        print(f"[TELEGRAM] ❌ Failed: {resp.status_code} – {resp.text}")
        return False


def send_document_to_telegram(photo_path: Path, caption: str) -> bool:
    """
    Fallback: ส่งเป็น document แทน photo
    (Telegram จำกัดภาพ sendPhoto ที่ 10 MB, sendDocument รองรับ 50 MB)
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    print("[TELEGRAM] Trying sendDocument as fallback …")

    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
            },
            files={"document": ("dashboard.png", f, "image/png")},
            timeout=60,
        )

    if resp.status_code == 200:
        print(f"[TELEGRAM] ✅ Sent as document!")
        return True
    else:
        print(f"[TELEGRAM] ❌ Document fallback failed: {resp.status_code} – {resp.text}")
        return False


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    report_date = get_report_date()
    send_time   = get_send_time_str()
    out_path    = SCREENSHOT_PATH.with_name(f"dashboard_{report_date.replace('-','')}.png")

    # ─── Capture (with retry) ───────────────────────────────────────
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            capture_screenshot(DASHBOARD_URL, out_path)
            break
        except Exception as e:
            print(f"[CAPTURE] Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt == MAX_RETRIES:
                print("[CAPTURE] All attempts failed. Aborting.")
                sys.exit(1)
            time.sleep(5)

    # ─── Send to Telegram ───────────────────────────────────────────
    caption = build_caption(report_date, send_time)
    file_size_mb = out_path.stat().st_size / 1024 / 1024

    # Telegram sendPhoto limit = 10 MB; ถ้าเกินใช้ sendDocument
    if file_size_mb <= 10:
        success = send_photo_to_telegram(out_path, caption)
    else:
        print(f"[TELEGRAM] File too large for sendPhoto ({file_size_mb:.1f} MB) → using sendDocument")
        success = send_document_to_telegram(out_path, caption)

    if not success:
        # Last resort: ส่ง text message แทน
        print("[TELEGRAM] Sending text-only message as last resort …")
        text_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(text_url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": caption + "\n\n⚠️ ไม่สามารถส่งภาพได้ กรุณาเปิด link โดยตรง",
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=30)
        sys.exit(1)

    print("[DONE] ✅ Complete!")


if __name__ == "__main__":
    main()
