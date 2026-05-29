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

def click_prev(page):
    """คลิกปุ่ม < หลายวิธี"""
    methods = [
        "button:has-text('<')",
        "[class*='prev']",
        "[class*='back']",
        "button:nth-child(1)",
    ]
    for selector in methods:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1000):
                btn.click()
                print("[NAV] Clicked prev via: " + selector)
                return True
        except Exception:
            pass
    # JavaScript fallback
    page.evaluate("""
        () => {
            const all = Array.from(document.querySelectorAll('button, [role=button], a'));
            const btn = all.find(el => el.textContent.trim() === '<' || el.innerHTML.includes('chevron-left') || el.innerHTML.includes('prev'));
            if (btn) btn.click();
        }
    """)
    return True

def navigate_to_date(page, target_date_str):
    target = datetime.strptime(target_date_str, "%d-%m-%Y").date()
    print("[NAV] Target: " + target_date_str)

    # อ่านวันที่ปัจจุบันบน Dashboard
    for attempt in range(30):
        try:
            date_text = page.locator("text=/\\d{2}-\\d{2}-\\d{4}/").first.inner_text(timeout=2000)
            current = datetime.strptime(date_text.strip(), "%d-%m-%Y").date()
            print("[NAV] Current: " + str(current) + " Target: " + str(target))
        except Exception:
            print("[NAV] Cannot read date, skipping navigation")
            return

        if current == target:
            print("[NAV] Date matched!")
            page.wait_for_timeout(2000)
            return

        if current > target:
            click_prev(page)
            page.wait_for_timeout(2000)
        else:
            # คลิก >
            try:
                page.locator("button:has-text('>')").first.click()
            except Exception:
                page.evaluate("() => { const all = Array.from(document.querySelectorAll('button')); const btn = all.find(el => el.textContent.trim() === '>'); if(btn) btn.click(); }")
            page.wait_for_timeout(2000)

    print("[NAV] Done after 30 attempts")

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
        page.set_default_timeout(30000)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)

        page.wait_for_timeout(5000)
        navigate_to_date(page, report_date)
        page.wait_for_timeout(4000)
        page.add_style_tag(content="::-webkit-scrollbar{display:none!important}")
        page.screenshot(path=str(out_path), full_page=True, type="png")
        browser.close()

    mb = out_path.stat().st_size / 1024 / 1024
    print("[CAPTURE] Saved " + str(round(mb,1)) + " MB -> " + str(out_path))

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
        print("[TELEGRAM] Sent! id=" + str(r.json()["result"]["message_id"]))
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
