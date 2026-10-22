from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
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


# ========================
# TÌM NÚT SIGN IN HỢP LỆ
# ========================
def dismiss_overlays(driver):
    """
    Đóng popup mềm để tránh click bị intercept.
    """
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
    """
    Click chắc hơn: thử click thường trước, fail thì fallback JS click.
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
    """
    Chờ phần tử xuất hiện + khả dụng rồi click với fallback.
    """
    element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))

    wait.until(
        lambda d: element.is_displayed()
        and element.is_enabled()
        and element.get_attribute("aria-disabled") != "true"
    )

    return robust_click(driver, element, description, uid=uid, attempt=attempt)


def is_element_interactable(driver, element):
    """
    Kiểm tra khả năng tương tác mà không phụ thuộc style màu.
    """
    try:
        if not element.is_displayed():
            return False

        class_name = (element.get_attribute("class") or "").lower()
        if any(flag in class_name for flag in ["disabled", "is-disabled", "done", "signed", "unsign"]):
            return False

        if (element.get_attribute("aria-disabled") or "").lower() == "true":
            return False

        computed = driver.execute_script(
            """
            const el = arguments[0];
            const style = window.getComputedStyle(el);
            return {
                display: style.display,
                visibility: style.visibility,
                pointerEvents: style.pointerEvents,
                opacity: style.opacity
            };
            """,
            element,
        )

        if computed["display"] == "none":
            return False
        if computed["visibility"] == "hidden":
            return False
        if computed["pointerEvents"] == "none":
            return False

        try:
            if float(computed["opacity"]) < 0.15:
                return False
        except Exception:
            pass

        return True
    except Exception:
        return False


def find_clickable_signin_buttons(driver, uid=None, attempt=None):
    """
    Tìm nút Sign in ĐANG ACTIVE (được phép click), loại trừ nút bị khóa.

    Dựa theo cấu trúc DOM thực tế:
    - Nút active:  <div class="relative handle">          (nền cam, không có <img> khóa)
    - Nút bị khóa: <div class="relative handle unsign">   (nền xám, có thêm <img> icon khóa)

    Trả về tuple (active_buttons, all_candidates):
    - active_buttons: các nút active, đã qua kiểm tra is_element_interactable
    - all_candidates: TẤT CẢ phần tử 'handle' Sign in tìm thấy (active + bị khóa),
      dùng để phân biệt "trang lỗi/chưa load được danh sách" (all_candidates rỗng)
      với "đã điểm danh hết, chỉ còn nút bị khóa" (all_candidates có nhưng active rỗng).
    """
    all_candidates = driver.find_elements(
        By.XPATH,
        "//span[normalize-space()='Check In' or normalize-space()='Sign in']"
        "/ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' handle ')][1]"
    )

    active_candidates = [
        c for c in all_candidates
        if "unsign" not in (c.get_attribute("class") or "").lower()
    ]

    log(
        f"Tìm thấy {len(all_candidates)} nút Sign in tổng "
        f"({len(active_candidates)} active tiềm năng, "
        f"{len(all_candidates) - len(active_candidates)} bị khóa)",
        uid, attempt,
    )

    active_buttons = []

    for i, btn in enumerate(active_candidates):
        try:
            if is_element_interactable(driver, btn):
                log(f"Nút active {i + 1} khả dụng -> chọn", uid, attempt)
                active_buttons.append(btn)
            else:
                log(f"Nút active {i + 1} không khả dụng -> bỏ qua", uid, attempt, level="WARN")

        except Exception as e:
            log(f"Lỗi kiểm tra nút active {i + 1}: {e}", uid, attempt, level="WARN")
            continue

    return active_buttons, all_candidates


def scroll_and_find_signin(driver, uid=None, attempt=None):
    """
    Scroll thông minh: quét toàn trang để gom tất cả nút Sign in active.

    Trả về tuple (active_buttons, total_signin_count):
    - active_buttons: danh sách nút active (đã dedup qua các vòng scroll)
    - total_signin_count: tổng số nút Sign in tìm thấy trên trang (active + bị khóa,
      đã dedup) - dùng để phân biệt "trang lỗi, không thấy gì" với "đã điểm danh hết".
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    same_height_count = 0
    seen_active_ids = set()
    seen_total_ids = set()
    active_buttons = []
    total_signin_count = 0

    for round_idx in range(1, 15):
        buttons, all_candidates = find_clickable_signin_buttons(driver, uid=uid, attempt=attempt)

        for candidate in all_candidates:
            candidate_id = getattr(candidate, "id", None)
            if candidate_id in seen_total_ids:
                continue
            seen_total_ids.add(candidate_id)
            total_signin_count += 1

        for btn in buttons:
            btn_id = getattr(btn, "id", None)
            if btn_id in seen_active_ids:
                continue

            seen_active_ids.add(btn_id)
            active_buttons.append(btn)

        driver.execute_script("window.scrollBy(0, Math.floor(window.innerHeight * 0.8));")
        time.sleep(0.35)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            same_height_count += 1
        else:
            same_height_count = 0
        last_height = new_height

        if same_height_count >= 3:
            log("Chiều cao trang không đổi nhiều lần, dừng scroll", uid, attempt, level="WARN")
            break

    return active_buttons, total_signin_count


def wait_for_success_message(driver, timeout=6):
    """
    Chờ toast success xuất hiện. Trả về True/False thay vì raise,
    để logic gọi ở nơi khác dễ xử lý theo từng lần click riêng lẻ.

    LƯU Ý QUAN TRỌNG:
    Toast 'el-message--success' của Element UI là transient (tự fade
    và biến mất khỏi DOM sau vài giây). Vì vậy hàm này PHẢI được gọi
    NGAY SAU mỗi lần click Sign in, không được gộp chung và gọi một
    lần duy nhất sau khi đã click hết tất cả các nút - nếu không toast
    của các lần click trước có thể đã biến mất trước khi WebDriverWait
    kịp poll, dẫn tới TimeoutException giả (false negative) dù thực tế
    đã nhận quà thành công.
    """
    success_xpath = (
        "//div[contains(@class,'el-message--success')]"
        "|//p[contains(@class,'el-message__content') and "
        "contains(translate(normalize-space(.),'SUCCESS','success'),'success')]"
    )

    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, success_xpath))
        )
        return True
    except TimeoutException:
        return False


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

        # Đóng popup nếu có (robust): thử các nút đóng trước, nếu không thì ESC + click rìa nhiều lần
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(0.4)

            # Thử click các nút Close/OK phổ biến
            close_xpaths = [
                "//button[contains(@class,'el-dialog__headerbtn')]",
                "//button[contains(@class,'close')]",
                "//button[normalize-space()='Close']",
                "//button[normalize-space()='OK']",
            ]
            clicked_any = False
            for xp in close_xpaths:
                for btn in driver.find_elements(By.XPATH, xp):
                    try:
                        if is_element_interactable(driver, btn):
                            robust_click(driver, btn, "Close popup", uid, attempt)
                            clicked_any = True
                            time.sleep(0.25)
                    except Exception:
                        pass

            # Nếu chưa đóng được bằng nút, thử ESC và click rìa nhiều lần
            if not clicked_any:
                for _ in range(5):
                    try:
                        body = driver.find_element(By.TAG_NAME, "body")
                        body.send_keys(Keys.ESCAPE)
                    except Exception:
                        pass

                    try:
                        driver.execute_script("window.scrollBy(0, 1);")
                        driver.execute_script("document.elementFromPoint(10, 10).click();")
                    except Exception:
                        pass

                    time.sleep(0.35)

        except Exception as e:
            log(f"Dismiss overlays (robust) lỗi, bỏ qua: {e}", uid, attempt, level="WARN")
        time.sleep(0.2)

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

        # Đóng popup nếu có (an toàn): chờ body xuất hiện, thử dismiss mà không raise
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(0.4)
            dismiss_overlays(driver)
        except Exception as e:
            log(f"Dismiss overlays (lần 2) lỗi, bỏ qua: {e}", uid, attempt, level="WARN")
        time.sleep(0.2)

        # ================================
        # SCROLL XUỐNG ĐỂ TÌM NÚT SIGN IN
        # ================================
        log("Đang scroll tìm nút Sign in...", uid, attempt)

        # Tìm nút Sign in active
        signin_buttons, total_signin_count = scroll_and_find_signin(driver, uid=uid, attempt=attempt)

        if not signin_buttons:
            if total_signin_count == 0:
                # Không thấy BẤT KỲ nút Sign in nào (kể cả bị khóa) -> khả năng
                # trang chưa load kịp, bị popup che, hoặc selector không khớp.
                # Đây là dấu hiệu lỗi, không phải đã điểm danh xong -> retry.
                log(
                    "Không tìm thấy nút Sign in nào trên trang (kể cả nút bị khóa) "
                    "-> nghi ngờ lỗi tải trang, coi là thất bại để retry",
                    uid, attempt, level="ERROR",
                )
                driver.save_screenshot(f"no_signin_found_{uid}_try{attempt}.png")
                return False

            # Có tìm thấy nút Sign in (nhưng toàn bộ đều bị khóa/unsign)
            # -> đã điểm danh hết, không còn gì để click.
            log(
                f"Tìm thấy {total_signin_count} nút Sign in nhưng tất cả đều bị khóa "
                "-> coi như đã điểm danh xong",
                uid, attempt,
            )
            return True

        # ================================
        # CLICK TỪNG NÚT + CHỜ SUCCESS NGAY SAU ĐÓ
        # ================================
        # QUAN TRỌNG: kiểm tra toast success NGAY SAU mỗi lần click,
        # KHÔNG gộp chung rồi chờ 1 lần ở cuối - vì toast tự biến mất
        # sau vài giây nên chờ trễ sẽ bị miss (false TimeoutException)
        # dù thực tế đã click và nhận quà thành công.
        clicked_any = False
        success_count = 0

        for idx, signin_btn in enumerate(signin_buttons, start=1):
            if robust_click(driver, signin_btn, f"Sign in #{idx}", uid=uid, attempt=attempt):
                clicked_any = True

                if wait_for_success_message(driver, timeout=6):
                    success_count += 1
                    log(f"Sign in #{idx} -> NHẬN QUÀ THÀNH CÔNG", uid, attempt)
                else:
                    log(
                        f"Sign in #{idx} -> không thấy toast success (có thể đã fade trước khi kịp bắt)",
                        uid,
                        attempt,
                        level="WARN",
                    )

                time.sleep(0.4)

        if not clicked_any:
            log("Không click được bất kỳ nút Sign in active nào", uid, attempt, level="ERROR")
            driver.save_screenshot(f"signin_click_fail_{uid}_try{attempt}.png")
            return False

        if success_count == 0:
            log(
                "Đã click nhưng không xác nhận được toast success nào",
                uid,
                attempt,
                level="WARN",
            )
            driver.save_screenshot(f"success_timeout_{uid}_try{attempt}.png")
            return False

        log(f"Tổng cộng {success_count}/{len(signin_buttons)} lần Sign in xác nhận thành công", uid, attempt)
        time.sleep(1.2)
        return True

    except Exception as e:
        log(f"Error: {e}", uid, attempt, level="ERROR")
        driver.save_screenshot(f"error_{uid}_try{attempt}.png")
        return False

    finally:
        try:
            driver.quit()
        except Exception as e:
            log(f"driver.quit() lỗi (bỏ qua): {e}", uid, attempt, level="WARN")


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
