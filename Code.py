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
# CẤU HÌNH CHROME HEADLESS
# ========================
def log(message, uid=None, attempt=None, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{ts}] [{level}]"

    if uid is not None:
        prefix += f" [UID:{uid}]"
    if attempt is not None:
        prefix += f" [TRY:{attempt}]"

    print(f"{prefix} {message}")


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=options)
    return driver


def dismiss_overlays(driver):
    """
    Đóng popup mềm để hạn chế click bị chặn.
    """
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
    except Exception:
        pass

    # Popup "How Gold Blocks work" chỉ đóng khi click ra vùng nền bên ngoài
    try:
        driver.execute_script("window.scrollBy(0, 1);")
        driver.execute_script(
            "var el = document.elementFromPoint(20, 20); if (el) el.click();"
        )
    except Exception:
        pass


def robust_click(driver, element, description, uid=None, attempt=None):
    """
    Ưu tiên native click, fallback JS click khi bị intercept.
    """
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
            uid,
            attempt,
            level="WARN",
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


LOWER = "translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
SUCCESS_XPATH = (
    f"//span[contains(@class,'success-title') and contains({LOWER},'redemption successful')]"
    f"|//div[contains(@class,'el-message--success') and contains({LOWER},'success')]"
)
ERROR_XPATH = "//div[contains(@class,'el-message--error') or contains(@class,'el-message--warning')]"
# Lỗi vĩnh viễn: thử lại cũng vô ích (code sai / đã dùng / hết hạn)
PERMANENT_ERROR_KEYWORDS = ("already", "used", "invalid", "incorrect", "wrong", "expired", "not exist", "not found")


def wait_for_redeem_result(driver):
    """
    Chờ kết quả đổi code. Trả về ("success", "") hoặc ("error", nội dung thông báo).
    Raise TimeoutException nếu không thấy gì.
    """

    def check(d):
        if d.find_elements(By.XPATH, SUCCESS_XPATH):
            return ("success", "")
        errors = d.find_elements(By.XPATH, ERROR_XPATH)
        if errors:
            return ("error", errors[0].text.strip())
        return False

    return WebDriverWait(driver, 12).until(check)


def close_success_popup(driver, uid=None, attempt=None):
    """
    Đóng popup 'Redemption successful' bằng nút close, fallback phím ESC.
    """
    close_xpath = (
        "//div[contains(@class,'dialog-header-row')]//i[contains(@class,'close-btn')]"
        "|//button[@aria-label='Close' and contains(@class,'el-dialog__headerbtn')]"
    )
    popup_xpath = "//span[contains(@class,'success-title')]"

    clicked = False
    try:
        # Chỉ chọn nút close đang hiển thị (DOM có thể chứa nhiều dialog ẩn cùng class)
        visible = [b for b in driver.find_elements(By.XPATH, close_xpath) if b.is_displayed()]
        if visible:
            clicked = robust_click(driver, visible[0], "Close popup", uid, attempt)
    except Exception:
        pass

    if not clicked:
        log("Không click được nút close, dùng ESC", uid, attempt, level="WARN")
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass

    try:
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.XPATH, popup_xpath))
        )
    except TimeoutException:
        # Thử ESC lần nữa nếu popup vẫn còn
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            WebDriverWait(driver, 3).until(
                EC.invisibility_of_element_located((By.XPATH, popup_xpath))
            )
        except Exception:
            log("Popup vẫn chưa đóng", uid, attempt, level="WARN")
    time.sleep(0.5)


def fill_code(driver, wait, code):
    """
    Xóa code cũ (kể cả khi Vue không nhận .clear()) rồi nhập code mới.
    """
    code_input = wait.until(
        EC.visibility_of_element_located(
            (
                By.XPATH,
                "//input[@placeholder='Enter Gift Code' or @placeholder='Enter the code']",
            )
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", code_input)
    time.sleep(0.3)

    code_input.click()
    code_input.send_keys(Keys.CONTROL, "a")
    code_input.send_keys(Keys.BACKSPACE)
    code_input.clear()
    code_input.send_keys(code)


# ========================
# LOGIC CHO 1 ACCOUNT
# ========================
def run_account(uid, codes, attempt=1):
    """
    Đăng nhập 1 lần, đổi lần lượt các code trong `codes`.
    Trả về list các code đổi thất bại (rỗng = tất cả thành công).
    """
    log(f"Start account ({len(codes)} code)", uid=uid, attempt=attempt)
    failed = list(codes)

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

        # Đóng popup nếu có
        dismiss_overlays(driver)
        time.sleep(0.4)

        # Click LOGIN
        if not wait_and_click(driver, wait, "//span[text()='LOGIN']", "LOGIN", uid, attempt):
            raise RuntimeError("Không click được LOGIN")

        # Nhập UID
        uid_input = wait.until(
            EC.visibility_of_element_located((By.XPATH, "//input[@placeholder='Enter your UID...']"))
        )
        uid_input.clear()
        uid_input.send_keys(uid)
        log("Đã nhập UID", uid, attempt)

        # Click Check (chờ button không bị disabled)
        if not wait_and_click(
            driver,
            wait,
            "//button[contains(@class,'check-btn') and not(@disabled)]",
            "Check",
            uid,
            attempt,
        ):
            raise RuntimeError("Không click được Check")

        # Click Confirm
        if not wait_and_click(
            driver,
            wait,
            "//button[normalize-space()='Confirm' and not(@disabled)]",
            "Confirm",
            uid,
            attempt,
        ):
            raise RuntimeError("Không click được Confirm")

        # Chờ về lại trang chính
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//strong[contains(text(),'How Gold Blocks work')]")
            )
        )
        time.sleep(0.8)

        # Đóng popup nếu có
        dismiss_overlays(driver)
        time.sleep(0.4)

        # ================================
        # TÌM VÀ ĐIỀN VÀO Ô NHẬP CODE
        # ================================
        for idx, code in enumerate(codes, 1):
            log(f"Code {idx}/{len(codes)}: {code}", uid, attempt)

            try:
                fill_code(driver, wait, code)
                log(f"Đã nhập code: {code}", uid, attempt)

                if not wait_and_click(
                    driver,
                    wait,
                    "//button[contains(@class,'submit-btn') and normalize-space()='Confirm' and not(@disabled)]",
                    "Redeem Confirm",
                    uid,
                    attempt,
                ):
                    raise RuntimeError("Không click được Confirm redeem")

                time.sleep(0.8)
                status, message = wait_for_redeem_result(driver)

                if status == "success":
                    log(f"ĐỔI CODE THÀNH CÔNG: {code}", uid, attempt)
                    failed.remove(code)
                    # Đóng popup để chuẩn bị nhập code kế tiếp
                    close_success_popup(driver, uid, attempt)
                elif any(k in message.lower() for k in PERMANENT_ERROR_KEYWORDS):
                    log(f"Code {code} bị từ chối, bỏ qua không thử lại: {message}", uid, attempt, level="WARN")
                    failed.remove(code)
                else:
                    log(f"Code {code} lỗi tạm thời: {message}", uid, attempt, level="WARN")
                time.sleep(0.8)

            except TimeoutException:
                log(
                    f"Timeout ở bước nhập/đổi code ({code}), xem ảnh redeem_timeout để biết dừng ở đâu",
                    uid,
                    attempt,
                    level="WARN",
                )
                driver.save_screenshot(f"redeem_timeout_{uid}_{code}_try{attempt}.png")
            except Exception as e:
                log(f"Lỗi với code {code}: {e}", uid, attempt, level="ERROR")
                driver.save_screenshot(f"error_{uid}_{code}_try{attempt}.png")

        return failed

    except Exception as e:
        log(f"Error: {e}", uid, attempt, level="ERROR")
        driver.save_screenshot(f"error_{uid}_try{attempt}.png")
        return failed

    finally:
        driver.quit()


# ========================
# RETRY LOGIC
# ========================
def run_account_with_retry(uid, codes, max_retry=3):
    attempt = 0
    pending = list(codes)  # chỉ thử lại những code chưa đổi được

    while attempt < max_retry:
        current_try = attempt + 1
        log(f"Attempt {current_try}/{max_retry}", uid=uid, attempt=current_try)

        pending = run_account(uid, pending, attempt=current_try)
        if not pending:
            log("DONE account", uid=uid, attempt=current_try)
            print()
            return True

        log(f"Còn {len(pending)} code chưa đổi: {pending}", uid=uid, attempt=current_try, level="WARN")
        attempt += 1
        sleep_time = random.uniform(3, 6)
        log(f"Retry sau {sleep_time:.2f}s...", uid=uid, attempt=current_try, level="WARN")
        print()
        time.sleep(sleep_time)

    log(f"FAILED sau {max_retry} lần thử, code lỗi: {pending}", uid=uid, level="ERROR")
    print()
    return False

    
# ========================
# ĐẶT CODE CẦN ĐỔI Ở ĐÂY
# ========================
REDEEM_CODES = [
    "GBEE2C34A5",
]


# ========================
# CHẠY TUẦN TỰ + RETRY
# ========================
def main():
    for acc in ACCOUNT_IDS:
        run_account_with_retry(acc, REDEEM_CODES, max_retry=3)

        sleep_time = random.uniform(3, 6)
        log(f"Sleep {sleep_time:.2f}s trước account tiếp theo")
        print()
        time.sleep(sleep_time)

    log("DONE ALL")


if __name__ == "__main__":
    main()