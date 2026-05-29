#!/usr/bin/env python3
import os, sys, time, requests, pytz
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

DASHBOARD_URL    = os.environ.get("DASHBOARD_URL", "https://ithcvopt-del.github.io/Production-Seng/")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TZ_ICT           = pytz.timezone("Asia/Bangkok")
WORKSPACE        = Path(os.environ.get("GITHUB_WORKSPACE", "."))

def get_report_date():
    now = datetime.now(TZ_ICT)
    d   = now.date() if now.hour >= 8 else (now - timedelta(days=1)).date()
    result = d.strftime("%d-%m-%Y")
    print(f"[DATE] ICT={now.strftime('%d/%m/%Y %H:%M')} -> report={result}")
    return result

def navigate_to_date(page, target_date_str):
    target = datetime.strptime(target_date_str, "%d-%m-%Y").date()
    print(f"[NAV] Target date: {target_date_str}")
    for attempt in range(60):
        try:
            date_text = page.locator("text=/\\d{2}-\\d{2}-\\d{4}/").first.inner_text(timeout=3000)
            current   = datetime.strptime(date_text.strip(), "%d-%m-%Y").date()
            print(f"[NAV] Dashboard shows: {date_text.strip()}")
        except Exception as e:
            print(f"[NAV] Cannot read date: {e}")
            break
        if current == target:
            print("[NAV] Date matched!")
            page.wait_for_timeout(3000)
            break
        elif current > target:
            try:
                page.locator("button:has-text('<')").first.click()
            except Exception:
                page.evaluate("() => { const btns = document.querySelectorAll('button'); for(const b of btns){ if(b.textContent.trim()==='<'){b.click();break;} } }")
            page.wait_for_timeout(1500)
        else:
            try:
                page.locator("button:has-text('>')").first.click()
            except Exception:
                page.evaluate("() => { const btns = document.querySelectorAll('button'); for(const b of btns){ if(b.textContent.trim()==='>'){ b.click();break;} } }")
            page.wait_for_timeout(1500)

def capture(url, out_path, report_date):
    print(f"[CAPTURE] Opening {url}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            locale="th-TH",
            timezone_id="Asia/Bangkok"
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=40000)
        except PWTimeoutError:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(6000)
        navigate_to_date(page, report_date)
        page.wait_for_timeout(5000)
        page.add_style_tag(content="::-webkit-scrollbar{display:none!important}")
        page.screenshot(path=str(out_path), full_page=True, type="png")
        browser.close()
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"[CAPTURE] Saved {out_path} ({size_mb:.1f} MB)")

def send_telegram(photo_path, report_date):
    now_str = datetime.now(TZ_ICT).strftime("%d/%m/%Y %H:%M")
    caption = (
        f"Production Dashboard\n"
        f"reportdate: {report_date}\n"
        f"senttime: {now_str} ICT\n"
        f"Dashboard: {DASHBOARD_URL}"
    )
    size_mb = photo_path.stat().st_size / 1024 / 1024
    method  = "sendPhoto"  if size_mb <= 10 else "sendDocument"
    field   = "photo"      if size_mb <= 10 else "document"
    print(f"[TELEGRAM] Sending via {method} ({size_mb:.1f} MB)...")
    with open(photo_path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={field: ("dashboard.png", f, "image/png")},
            timeout=60
        )
    if r.status_code == 200:
        print(f"[TELEGRAM] Sent! id={r.json()['result']['message_id']}")
        return True
    else:
        print(f"[TELEGRAM] Failed: {r.status_code}: {r.text}")
        return False

def main():
    if not TELEGRAM_TOKEN:
        print("[ERROR] TELEGRAM_TOKEN not set")
        sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        print("[ERROR] TELEGRAM_CHAT_ID not set")
        sys.exit(1)
    report_date = get_report_date()
    out_path = WORKSPACE / f"screenshot_{report_date.replace('-', '')}.png"
    print(f"[INFO] Output path: {out_path}")
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
    print("[DONE] Complete!")

if __name__ == "__main__":
    main()
