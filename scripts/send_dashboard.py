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
    d = now.date() if now.hour >= 8 else (now - timedelta(days=1)).date()
    result = d.strftime("%d-%m-%Y")
    print("[DATE] " + now.strftime("%d/%m/%Y %H:%M") + " -> " + result)
    return result

def navigate_to_date(page, target_date_str):
    target = datetime.strptime(target_date_str, "%d-%m-%Y").date()
    print("[NAV] Target: " + target_date_str)
    start_time = time.time()

    for attempt in range(20):
        # หมดเวลา 60 วินาที → หยุด
        if time.time() - start_time > 60:
            print("[NAV] Timeout 60s, stop navigation")
            break

        try:
            date_text = page.locator("text=/\\d{2}-\\d{2}-\\d{4}/").first.inner_text(timeout=2000)
            current = datetime.strptime(date_text.strip(), "%d-%m-%Y").date()
            print("[NAV] Current: " + str(current))
        except Exception:
            print("[NAV] Cannot read date, skip")
            break

        if current == target:
            print("[NAV] Matched!")
            page.wait_for_timeout(2000)
            return

        diff = (current - target).days
        print("[NAV] Diff: " + str(diff) + " days")

        if diff > 0:
            # คลิก < ด้วย JavaScript
            clicked = page.evaluate("""
                () => {
                    const all = Array.from(document.querySelectorAll('button, a, span, div'));
                    const btn = all.find(el =>
                        el.textContent.trim() === '<' ||
                        el.textContent.trim() === '‹' ||
                        el.getAttribute('aria-label') === 'previous' ||
                        el.className.includes('prev')
                    );
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            print("[NAV] Clicked prev: " + str(clicked))
        else:
            clicked = page.evaluate("""
                () => {
                    const all = Array.from(document.querySelectorAll('button, a, span, div'));
                    const btn = all.find(el =>
                        el.textContent.trim() === '>' ||
                        el.textContent.trim() === '›' ||
                        el.getAttribute('aria-label') === 'next' ||
                        el.className.includes('next')
                    );
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            print("[NAV] Clicked next: " + str(clicked))

        page.wait_for_timeout(2000)

    print("[NAV] Done")

def capture(url, out_path, report_date):
    print("[CAPTURE] " + url)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            locale="th-TH",
            timezone_id="Asia/Bangkok"
        )
        page = ctx.new_page()
        page.set_default_timeout(20000)
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(5000)
        navigate_to_date(page, report_date)
        page.wait_for_timeout(3000)
        page.add_style_tag(content="::-webkit-scrollbar{display:none!important}")
        page.screenshot(path=str(out_path), full_page=True, type="png")
        browser.close()
    mb = out_path.stat().st_size / 1024 / 1024
    print("[CAPTURE] Saved " + str(round(mb,1)) + " MB")

def send_telegram(photo_path, report_date):
    now_str = datetime.now(TZ_ICT).strftime("%d/%m/%Y %H:%M")
    caption = "Production Dashboard\nDate: " + report_date + "\nSent: " + now_str + " ICT"
    mb = photo_path.stat().st_size / 1024 / 1024
    method = "sendPhoto" if mb <= 10 else "sendDocument"
    field  = "photo"     if mb <= 10 else "document"
    with open(photo_path, "rb") as f:
        r = requests.post(
            "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/" + method,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={field: ("dashboard.png", f, "image/png")},
            timeout=60
        )
    if r.status_code == 200:
        print("[TELEGRAM] Sent!")
        return True
    print("[TELEGRAM] Failed: " + str(r.status_code))
    return False

def main():
    if not TELEGRAM_TOKEN:
        print("[ERROR] TELEGRAM_TOKEN not set"); sys.exit(1)
    if not TELEGRAM_CHAT_ID:
        print("[ERROR] TELEGRAM_CHAT_ID not set"); sys.exit(1)
    report_date = get_report_date()
    out_path = WORKSPACE / ("screenshot_" + report_date.replace("-","") + ".png")
    print("[INFO] Output: " + str(out_path))
    for attempt in range(1, 4):
        try:
            capture(DASHBOARD_URL, out_path, report_date)
            break
        except Exception as e:
            print("[CAPTURE] Attempt " + str(attempt) + " failed: " + str(e))
            if attempt == 3:
                sys.exit(1)
            time.sleep(5)
    if not send_telegram(out_path, report_date):
        sys.exit(1)
    print("[DONE] Complete!")

if __name__ == "__main__":
    main()
