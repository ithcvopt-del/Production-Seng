#!/usr/bin/env python3
"""
send_dashboard.py — แก้ปัญหา:
1. นำทาง Dashboard ไปยังวันที่ที่ถูกต้องก่อน capture
2. Logic วันที่: hour < 8 ICT → เมื่อวาน, hour >= 8 → วันนี้
"""

import os, sys, time, requests, pytz
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# ── Config ─────────────────────────────────────────────────────────
DASHBOARD_URL    = os.environ.get("DASHBOARD_URL", "https://ithcvopt-del.github.io/Production-Seng/")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TZ_ICT           = pytz.timezone("Asia/Bangkok")

def get_report_date():
    """คืนวันที่รายงาน: ICT hour < 8 → เมื่อวาน, >= 8 → วันนี้"""
    now = datetime.now(TZ_ICT)
    d   = now.date() if now.hour >= 8 else (now - timedelta(days=1)).date()
    result = d.strftime("%d-%m-%Y")   # DD-MM-YYYY
    print(f"[DATE] ICT={now.strftime('%d/%m/%Y %H:%M')} → report={result}")
    return result

def navigate_to_date(page, target_date_str):
    """
    คลิกปุ่ม < > บน Dashboard จนกว่าจะได้วันที่ที่ต้องการ
    target_date_str: DD-MM-YYYY
    """
    target = datetime.strptime(target_date_str, "%d-%m-%Y").date()
    print(f"[NAV] Target date: {target_date_str}")

    for attempt in range(60):   # max 60 ครั้ง (กัน infinite loop)
        # อ่านวันที่ปัจจุบันบน Dashboard
        try:
            date_text = page.locator("text=/\\d{2}-\\d{2}-\\d{4}/").first.inner_text(timeout=3000)
            current = datetime.strptime(date_text.strip(), "%d-%m-%Y").date()
            print(f"[NAV] Dashboard shows: {date_text.strip()}")
        except Exception as e:
            print(f"[NAV] Cannot read date: {e}")
            break

        if current == target:
            print(f"[NAV] ✅ Date matched!")
            page.wait_for_timeout(3000)   # รอ chart reload
            break
        elif current > target:
            # คลิก < (ย้อนหลัง)
            try:
                page.locator("button:has-text('<'), [aria-label*='prev'], [aria-label*='back']").first.click()
                print(f"[NAV] Clicked < (back)")
            except:
                # ลอง XPath
                page.evaluate("() => { const btns = document.querySelectorAll('button'); for(const b of btns){ if(b.textContent.trim()==='<') { b.click(); break; } } }")
            page.wait_for_timeout(1500)
        else:
            # คลิก > (ไปข้างหน้า)
            try:
                page.locator("button:has-text('>'), [aria-label*='next']").first.click()
                print(f"[NAV] Clicked > (forward)")
            except:
                page.evaluate("() => { const btns = document.querySelectorAll('button'); for(const b of btns){ if(b.textContent.trim()==='>')  { b.click(); break; } } }")
            page.wait_for_timeout(1500)
    else:
        print(f"[NAV] ⚠️ Could not navigate to target date after 60 attempts")

def capture(url, out_path, report_date):
    print(f"[CAPTURE] Opening {url}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-dev-shm-usage","--disable-gpu"]
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            locale="th-TH",
            timezone_id="Asia/Bangkok"
        )
        page = ctx.new_page()

        # โหลด Dashboard
        try:
            page.goto(url, wait_until="networkidle", timeout=40000)
        except PWTimeoutError:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)

        # รอ chart render ครั้งแรก
        print("[CAPTURE] Waiting for initial render...")
        page.wait_for_timeout(6000)

        # นำทางไปวันที่ที่ถูกต้อง
        navigate_to_date(page, report_date)

        # รอ chart render หลังเปลี่ยนวันที่
        page.wait_for_timeout(5000)

        # ซ่อน scrollbar
        page.add_style_tag(content="""
            ::-webkit-scrollbar { display: none !important; }
            * { scrollbar-width: none !important; }
        """)

        page.screenshot(path=str(out_path), full_page=True, type="png")
        browser.close()

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"[CAPTURE] ✅ Saved {out_path} ({size_mb:.1f} MB)")
    return size_mb

def send_telegram(photo_path, report_date):
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

    print(f"[TELEGRAM] Sending via {method} ({size_mb:.1f} MB)...")
    with open(photo_path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            data={"chat_id": TELEGRAM_CHAT_ID,
                  "caption": caption, "parse_mode": "Markdown"},
            files={field: ("dashboard.png", f, "image/png")},
            timeout=60
        )
    if r.status_code == 200:
        print(f"[TELEGRAM] ✅ Sent! id={r.json()['result']['message_id']}")
        return True
    else:
        print(f"[TELEGRAM] ❌ {r.status_code}: {r.text}")
        return False

def main():
    if not TELEGRAM_TOKEN:
        print("[ERROR] TELEGRAM_TOKEN not set"); sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        print("[ERROR] TELEGRAM_CHAT_ID not set"); sys.exit(1)

    report_date = get_report_date()
    out_path    = Path(f"/tmp/dashboard_{report_date.replace('-','')}.png")

    for attempt in range(1, 4):
        try:
            capture(DASHBOARD_URL, out_path, report_date)
            break
        except Exception as e:
            print(f"[CAPTURE] Attempt {attempt}/3 failed: {e}")
            if attempt == 3:
                sys.exit(1)
            time.sleep(5)

    if not send_telegram(out_path, report_date):
        sys.exit(1)

    print("[DONE] ✅ Complete!")

if __name__ == "__main__":
    main()
