from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import ddddocr
import time
from playwright.sync_api import sync_playwright

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
ocr = ddddocr.DdddOcr(show_ad=False)

@app.get("/sync")
def sync_attendance(user: str, passw: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # --- AUTO-RETRY LOOP (Max 5 attempts) ---
            login_success = False
            max_retries = 10
            
            for attempt in range(max_retries):
                page.goto("http://report.aldel.org/student_page.php", timeout=60000)
                page.fill('[name="studentid"]', user)
                page.fill('[name="studentpwd"]', passw)
                
                page.locator("#captcha").screenshot(path="cap.png")
                with open("cap.png", "rb") as f:
                    captcha_text = ocr.classification(f.read())
                
                page.fill('[name="captcha_code"]', captcha_text.strip())
                page.click('[name="student_submit"]')
                
                # Thoda wait karenge taaki page load ho sake
                page.wait_for_timeout(3000)
                
                # Check agar login ho gaya
                if page.url != "http://report.aldel.org/student_page.php":
                    login_success = True
                    break  # Login success, loop se bahar nikal jao
                else:
                    print(f"Captcha failed for {user}, trying again... (Attempt {attempt + 1})", flush=True)
            
            # Agar 5 baar try karne ke baad bhi login nahi hua (Maybe password galat ho)
            if not login_success:
                browser.close()
                return {"success": False, "error": "Login Failed. Shayad Password galat hai ya Captcha hard hai. Try Again!"}
                
            # --- SCRAPE ATTENDANCE ---
            page.goto("http://report.aldel.org/student/attendance_report.php")
            time.sleep(2)
            
            data = []
            rows = page.locator("table tr")
            for i in range(rows.count()):
                cols = rows.nth(i).locator("td")
                if cols.count() >= 4:
                    total = int(cols.nth(1).inner_text().strip())
                    present = int(cols.nth(2).inner_text().strip())
                    if total > 0:
                        pct = int(round((present / total) * 100))
                        data.append({
                            "name": cols.nth(0).inner_text().strip(),
                            "present": present,
                            "total": total,
                            "pct": pct
                        })
            
            browser.close()
            
            # Yeh log tere Render server pe print hoga dost ka ID dekhne ke liye!
            print(f"🚀 NAYA LOGIN AAYA: Dost {user} ne abhi EIMI use kiya! 🔥", flush=True)
            
            return {"success": True, "data": data}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
