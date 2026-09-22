from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import ddddocr
from playwright.sync_api import sync_playwright

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ocr = ddddocr.DdddOcr(show_ad=False)

@app.get("/")
def health_check():
    return {"status": "alive", "service": "attendpro"}

@app.get("/sync")
def sync_attendance(user: str, passw: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process"
                ]
            )
            
            context = browser.new_context(
                viewport={"width": 800, "height": 600},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            login_success = False
            max_retries = 6

            for attempt in range(max_retries):
                page.goto("http://report.aldel.org/student_page.php", timeout=30000)
                page.wait_for_selector("#captcha", timeout=10000)

                page.fill('[name="studentid"]', user)
                page.fill('[name="studentpwd"]', passw)

                # Direct memory bytes se captcha read hoga
                captcha_bytes = page.locator("#captcha").screenshot()
                captcha_text = ocr.classification(captcha_bytes).strip()

                page.fill('[name="captcha_code"]', captcha_text)
                page.click('[name="student_submit"]')

                # Form submit hone aur redirect hone ke liye wait
                page.wait_for_timeout(2500)

                # Check agar login successful hua aur URL badla
                if "student_page.php" not in page.url:
                    login_success = True
                    break
                else:
                    print(f"Captcha retry for {user}... (Attempt {attempt + 1})", flush=True)

            if not login_success:
                browser.close()
                return {"success": False, "error": "Login Failed. Password ya Captcha galat hai."}

            # Attendance report page scrape
            page.goto("http://report.aldel.org/student/attendance_report.php", timeout=25000)
            page.wait_for_timeout(1500)

            # Check agar portal par 'No Data Found.' likha hai ya table nahi hai
            if page.locator("text=No Data Found").count() > 0 or page.locator("table tr").count() == 0:
                browser.close()
                print(f"NO DATA: {user} ke portal par attendance data nahi mila", flush=True)
                return {"success": True, "data": []}

            data = []
            rows = page.locator("table tr")
            row_count = rows.count()

            for i in range(row_count):
                cols = rows.nth(i).locator("td")
                if cols.count() >= 4:
                    try:
                        total_str = cols.nth(1).inner_text().strip()
                        present_str = cols.nth(2).inner_text().strip()
                        if total_str.isdigit() and present_str.isdigit():
                            total = int(total_str)
                            present = int(present_str)
                            if total > 0:
                                pct = int(round((present / total) * 100))
                                data.append({
                                    "name": cols.nth(0).inner_text().strip(),
                                    "present": present,
                                    "total": total,
                                    "pct": pct
                                })
                    except Exception:
                        continue

            browser.close()
            print(f"NAYA LOGIN: {user} synced successfully", flush=True)
            return {"success": True, "data": data}

    except Exception as e:
        return {"success": False, "error": str(e)}
