from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time
import random
from accounts import ACCOUNT_IDS


# ========================
# LOGGING
# ========================
def log(message, uid=None, attempt=None, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{ts}] [{level}]"
    if uid is not None:
        prefix += f" [UID:{uid}]"
    if attempt is not None:
        prefix += f" [TRY:{attempt}]"
    print(f"{prefix} {message}")


# ========================
# CHROME HEADLESS
# ========================
def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.page_load_strategy = "eager"
    return webdriver.Chrome(options=options)


# ========================
# HELPERS
# ========================
def dismiss_overlays(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
    except Exception:
        pass
    try:
        driver.execute_script("window.scrollBy(0, 1);")
        driver.execute_script("document.elementFromPoint(20, 20).click();")
    except Exception:
        pass


def robust_click(driver, element, description, uid=None, attempt=None):
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            element,
        )
        time.sleep(0.2)
    except Exception:
        pass

    try:
        element.click()
        log(f"Click thành công ({description}) bằng native click", uid, attempt)
        return True
    except Exception as native_err:
        log(
            f"Native click fail ({description}): {native_err}. Thử JS click...",
            uid, attempt, level="WARN",
        )

    try:
        driver.execute_script("arguments[0].click();", element)
        log(f"Click thành công ({description}) bằng JS click", uid, attempt)
        return True
    except Exception as js_err:
        log(f"JS click fail ({description}): {js_err}", uid, attempt, level="ERROR")
        return False


def wait_and_click(driver, wait, xpath, description, uid=None, attempt=None):
    element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
    wait.until(
        lambda d: element.is_displayed()
        and element.is_enabled()
        and element.get_attribute("aria-disabled") != "true"
    )
    return robust_click(driver, element, description, uid=uid, attempt=attempt)


# ========================
# ĐỌC SỐ LƯỢT DRAW CÒN LẠI
# ========================
def get_draws_left(driver, uid=None, attempt=None):
    """
    Đọc số lượt từ <span class="remain-tip ...">Draws left：N</span>
    Trả về số nguyên, hoặc 0 nếu không đọc được.
    """
    try:
        span = driver.find_element(By.CSS_SELECTOR, "span.remain-tip")
        text = span.text.strip()  # e.g. "Draws left：3"
        # Tách số ở cuối
        parts = text.replace("：", ":").split(":")
        draws = int(parts[-1].strip())
        log(f"Draws left: {draws}", uid, attempt)
        return draws
    except Exception as e:
        log(f"Không đọc được draws left: {e}", uid, attempt, level="WARN")
        return 0


# ========================
# LOGIC DRAW LOOP
# ========================
def run_draws(driver, wait, uid=None, attempt=None):
    """
    Lặp Single Draw cho đến khi Draws left = 0.
    """
    draws_done = 0

    while True:
        draws_left = get_draws_left(driver, uid, attempt)

        if draws_left <= 0:
            log(f"Hết lượt draw. Tổng đã quay: {draws_done}", uid, attempt)
            break

        # Click nút Single Draw
        try:
            draw_btn = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "button.action-btn")
                )
            )
            if not robust_click(driver, draw_btn, "Single Draw", uid, attempt):
                log("Không click được nút Single Draw", uid, attempt, level="ERROR")
                driver.save_screenshot(f"draw_click_fail_{uid}_try{attempt}_n{draws_done}.png")
                break
        except Exception as e:
            log(f"Lỗi tìm nút Single Draw: {e}", uid, attempt, level="ERROR")
            driver.save_screenshot(f"draw_btn_err_{uid}_try{attempt}_n{draws_done}.png")
            break

        # Chờ popup "Congratulations on getting"
        try:
            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class,'title') and contains(text(),'Congratulations')]")
                )
            )
            log("Popup kết quả xuất hiện", uid, attempt)
        except TimeoutException:
            log("Timeout chờ popup kết quả", uid, attempt, level="WARN")
            driver.save_screenshot(f"popup_timeout_{uid}_try{attempt}_n{draws_done}.png")
            break

        # Click nút Confirm để đóng popup
        try:
            confirm_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@class,'close-btn') and normalize-space()='Confirm']")
                )
            )
            if not robust_click(driver, confirm_btn, "Confirm (đóng popup)", uid, attempt):
                log("Không click được Confirm", uid, attempt, level="ERROR")
                driver.save_screenshot(f"confirm_fail_{uid}_try{attempt}_n{draws_done}.png")
                break
        except Exception as e:
            log(f"Lỗi tìm nút Confirm: {e}", uid, attempt, level="ERROR")
            driver.save_screenshot(f"confirm_err_{uid}_try{attempt}_n{draws_done}.png")
            break

        draws_done += 1
        log(f"Draw #{draws_done} hoàn thành", uid, attempt)

        # Chờ popup đóng hẳn trước lần sau
        try:
            wait.until(
                EC.invisibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'title') and contains(text(),'Congratulations')]")
                )
            )
        except Exception:
            time.sleep(0.8)

        time.sleep(random.uniform(0.4, 0.8))

    return draws_done


# ========================
# LOGIC CHO 1 ACCOUNT
# ========================
def run_account(uid, attempt=1):
    log("Start account", uid=uid, attempt=attempt)

    driver = create_driver()
    wait = WebDriverWait(driver, 15)

    try:
        driver.get("https://topheroes.pay-store.rivergame.net/")

        # Chờ trang load
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//strong[contains(text(),'How Gold Blocks work')]")
            )
        )
        time.sleep(0.8)

        dismiss_overlays(driver)
        time.sleep(0.4)

        # Click LOGIN
        if not wait_and_click(driver, wait, "//span[text()='LOGIN']", "LOGIN", uid, attempt):
            raise RuntimeError("Không click được LOGIN")

        # Nhập UID
        uid_input = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//input[@placeholder='Enter your UID...']")
            )
        )
        uid_input.clear()
        uid_input.send_keys(uid)
        log("Đã nhập UID", uid, attempt)

        # Click Check
        if not wait_and_click(
            driver, wait,
            "//button[contains(@class,'check-btn') and not(@disabled)]",
            "Check", uid, attempt,
        ):
            raise RuntimeError("Không click được Check")

        # Click Confirm
        if not wait_and_click(
            driver, wait,
            "//button[normalize-space()='Confirm' and not(@disabled)]",
            "Confirm", uid, attempt,
        ):
            raise RuntimeError("Không click được Confirm")

        # Chờ về lại trang chính
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//strong[contains(text(),'How Gold Blocks work')]")
            )
        )
        time.sleep(0.8)

        dismiss_overlays(driver)
        time.sleep(0.4)

        # ================================
        # KIỂM TRA LƯỢT DRAW
        # ================================
        draws_left = get_draws_left(driver, uid, attempt)

        if draws_left <= 0:
            log("Không còn lượt draw", uid, attempt, level="WARN")
            return True  # Không có lượt nhưng không phải lỗi

        log(f"Bắt đầu draw với {draws_left} lượt", uid, attempt)
        total = run_draws(driver, wait, uid, attempt)
        log(f"Hoàn thành {total} lượt draw", uid, attempt)
        return True

    except Exception as e:
        log(f"Error: {e}", uid, attempt, level="ERROR")
        driver.save_screenshot(f"error_{uid}_try{attempt}.png")
        return False

    finally:
        driver.quit()


# ========================
# RETRY LOGIC
# ========================
def run_account_with_retry(uid, max_retry=3):
    attempt = 0

    while attempt < max_retry:
        current_try = attempt + 1
        log(f"Attempt {current_try}/{max_retry}", uid=uid, attempt=current_try)

        if run_account(uid, attempt=current_try):
            log("DONE account", uid=uid, attempt=current_try)
            print()
            return True

        attempt += 1
        sleep_time = random.uniform(3, 6)
        log(f"Retry sau {sleep_time:.2f}s...", uid=uid, attempt=current_try, level="WARN")
        print()
        time.sleep(sleep_time)

    log(f"FAILED sau {max_retry} lần thử", uid=uid, level="ERROR")
    print()
    return False


# ========================
# CHẠY TUẦN TỰ + RETRY
# ========================
for acc in ACCOUNT_IDS:
    run_account_with_retry(acc, max_retry=3)

    sleep_time = random.uniform(3, 6)
    log(f"Sleep {sleep_time:.2f}s trước account tiếp theo")
    print()
    time.sleep(sleep_time)

log("DONE ALL")