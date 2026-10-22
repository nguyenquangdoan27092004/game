import pyautogui
import time
import pygetwindow as gw
import ctypes
import os
import cv2
import numpy as np
from PIL import Image

from app_paths import app_dir, fix_console_encoding

fix_console_encoding()

# Fix DPI Scaling để tọa độ không bị lệch
ctypes.windll.shcore.SetProcessDpiAwareness(1)

# pyautogui mặc định tự nghỉ 0.1s sau MỖI lệnh moveTo/click/press (kể cả 2 lần
# esc mỗi vòng) - hạ xuống để bot phản ứng nhanh hơn. Đừng đặt về 0 hẳn, vẫn
# nên giữ 1 khoảng nghỉ nhỏ để game kịp nhận input và tránh bị hệ thống
# chống bot phát hiện thao tác quá máy móc.
pyautogui.PAUSE = 0.02
MOVE_DURATION = 0  # giây di chuột tới nút trước khi click (0 = tức thì, kém "mượt" hơn)

BUTTON_DIR = os.path.join(app_dir(), "buttons_2")
DEBUG_DIR = os.path.join(app_dir(), "debug")

# --- CẤU HÌNH CHUỖI NÚT CẦN CLICK TẠI ĐÂY ---
# type "image" (mặc định):
#   image/images : 1 tên file HOẶC danh sách nhiều tên file ảnh trong buttons/.
#                  Khi có nhiều ảnh, bot thử khớp lần lượt, ảnh nào khớp
#                  trước thì click ảnh đó - dùng khi cùng 1 nút có thể xuất
#                  hiện ở nhiều trạng thái khác nhau (VD: đầy đủ hoặc bị
#                  panel che khuất một phần).
#   confidence   : độ khớp ảnh (0-1), thấp hơn = dễ khớp hơn nhưng dễ nhận nhầm
#   optional     : True nếu nút có thể đã ở trạng thái "đã chọn" và không còn
#                  xuất hiện nữa -> không tìm thấy KHÔNG phải lỗi
#   timeout      : giây tối đa chờ tìm nút này trước khi bỏ qua bước
#   skip_if_images: danh sách ảnh trạng thái "đã chọn" (có khung góc trang
#                  trí...) - nếu thấy 1 trong các ảnh này thì bỏ qua bước
#                  luôn, không cần tìm/click gì thêm và không phải chờ timeout.
# type "coord": click thẳng theo toạ độ OFFSET SO VỚI TÂM cửa sổ (không phải
#   góc trái/trên) - vì popup trong game luôn canh giữa màn hình, dùng offset
#   theo tâm sẽ vẫn đúng kể cả khi bạn đổi kích thước cửa sổ. Dùng cho nút bị
#   khuất/che một phần bởi panel nên không match ảnh được, nhưng vẫn có thể
#   click trúng. Lấy dx, dy bằng show_mouse_pos.py.
#   once       : True nếu chỉ cần click 1 lần xuyên suốt cả quá trình chạy
# Mọi type đều có "delay": giây chờ sau khi click thành công.
BUTTONS = [
    {"type": "image", "image": "button_1.png", "delay": 0.25, "confidence": 0.85, "optional": False, "timeout": 5},
    # Nút filter "Enemy" - chỉ cần kiểm tra/click ĐÚNG 1 LẦN xuyên suốt cả quá
    # trình chạy (once=True) -> từ lần thứ 2 trở đi bỏ qua hẳn, không tốn
    # thời gian tìm ảnh nữa.
    {
        "type": "image",
        "image": "button_2.png",
        "delay": 0.25,
        "confidence": 0.85,
        "optional": True,
        "timeout": 1,
        "once": True,
        "name": "button_2_enemy_filter",
    },
    # Chọn mục tiêu (card trong danh sách): tuỳ lúc card hiển thị đầy đủ hay bị
    # panel che một phần mà dùng ảnh khác nhau. type "select_card" phân biệt
    # "đã chọn" / "chưa chọn" bằng KHUNG GÓC MÀU CAM (không so cả card, vì card
    # chưa chọn vẫn khớp ảnh card đã chọn tới ~0.92).
    #   images          : ảnh card CHƯA chọn (đầy đủ / bị che) - dùng để click
    #   selected_images : ảnh card ĐÃ chọn (có khung góc cam)
    # once chỉ được đánh dấu khi ĐÃ click hoặc ĐÃ thấy khung "đã chọn" - nếu
    # không thấy card thì lần sau thử lại.
    {
        "type": "select_card",
        "images": ["button_3.png", "button_3(3).png"],
        "selected_images": ["button_3(2).png", "button_3(4).png"],
        "delay": 0.25,
        "confidence": 0.8,
        "timeout": 3,
        "once": True,
        "name": "button_3_target",
    },
    # Cách dự phòng nếu ảnh vẫn không khớp ổn định: click thẳng theo toạ độ
    # (offset so với tâm cửa sổ, lấy bằng show_mouse_pos.py). Đổi "type" của
    # bước trên thành "coord" và bật dòng dưới nếu muốn dùng lại cách này.
    # {"type": "coord", "dx": None, "dy": None, "delay": 0.5, "once": True, "name": "button_3_target"},
    {"type": "image", "image": "button_4.png", "delay": 0.25, "confidence": 0.85, "optional": False, "timeout": 5},
    {"type": "image", "image": "button_5.png", "delay": 0.6, "confidence": 0.85, "optional": False, "timeout": 5},
    # button_6.png có phần đồng hồ đếm ngược dưới chữ "Go" luôn thay đổi nên
    # không bao giờ khớp 100% với ảnh mẫu -> hạ confidence để chấp nhận sai
    # lệch ở vùng số, phần chữ "Go" + khung + icon đồng hồ vẫn phải khớp.
    {"type": "image", "image": "button_6.png", "delay": 0.25, "confidence": 0.7, "optional": False, "timeout": 5},
]

# Ảnh chữ "Idle" trong ô Queue - dùng để biết còn đội rảnh hay không.
# Chụp bằng: python capture_button.py idle.png (khoanh sát chữ "Idle").
IDLE_IMAGES = ["idle.png"]
IDLE_CONFIDENCE = 0.85
IDLE_CHECK_INTERVAL = 0.5  # giây giữa mỗi lần kiểm tra còn đội Idle hay không

# Khung góc "đã chọn" màu cam (HSV) và tỉ lệ pixel cam của ảnh mẫu phải xuất hiện
# lại trên màn hình để coi là đã chọn.
SELECTED_ORANGE_LOW = (5, 120, 150)
SELECTED_ORANGE_HIGH = (22, 255, 255)
SELECTED_MIN_FRACTION = 0.5

_clicked_once = set()  # theo dõi các bước "once" đã click trong lần chạy này

FIND_INTERVAL = 0.08  # giây giữa mỗi lần thử tìm lại trong lúc chờ 1 nút


def get_search_region(win):
    """Tính vùng tìm kiếm hợp lệ từ toạ độ cửa sổ.

    QUAN TRỌNG: pyautogui.locateCenterOnScreen() cắt vùng tìm kiếm bằng
    numpy slicing (haystack[top:top+h, left:left+w]). Nếu left/top ÂM (rất
    hay gặp trên Windows 10/11 vì GetWindowRect tính luôn viền resize vô
    hình, ví dụ left=-9), numpy sẽ hiểu chỉ số âm là "đếm từ cuối mảng"
    thay vì cắt về 0 như PIL .crop() vẫn làm -> vùng bị cắt sai hoàn toàn,
    khiến nút không bao giờ khớp dù ảnh mẫu đúng. Vì vậy phải kẹp left/top
    về >= 0 trước khi dùng, đồng thời co width/height tương ứng.
    """
    left = max(0, win.left)
    top = max(0, win.top)
    right = win.left + win.width
    bottom = win.top + win.height
    width = right - left
    height = bottom - top
    return (left, top, width, height)


def _locate_candidate(image_name, region, confidence):
    """Thử tìm 1 ảnh mẫu trong vùng chỉ định. Trả về (location, lỗi) - lỗi là
    chuỗi mô tả nếu ảnh thiếu file hoặc lớn hơn vùng tìm kiếm, ngược lại None."""
    image_path = os.path.join(BUTTON_DIR, image_name)
    if not os.path.exists(image_path):
        return None, f"⚠️  Thiếu ảnh mẫu: {image_path}"

    # Ảnh mẫu (needle) không được lớn hơn vùng tìm kiếm (haystack), nếu không
    # pyautogui sẽ raise ValueError thay vì trả về "không tìm thấy".
    with Image.open(image_path) as img:
        img_w, img_h = img.size
    region_w, region_h = region[2], region[3]
    if img_w > region_w or img_h > region_h:
        return None, (
            f"⚠️  Ảnh '{image_name}' ({img_w}x{img_h}) lớn hơn vùng cửa sổ đang tìm "
            f"({region_w}x{region_h}) -> có thể bắt nhầm cửa sổ game hoặc ảnh chụp "
            f"sai độ phân giải."
        )

    try:
        location = pyautogui.locateCenterOnScreen(
            image_path, region=region, confidence=confidence, grayscale=True
        )
    except (pyautogui.ImageNotFoundException, ValueError):
        location = None

    return location, None


def any_image_present(image_names, region, confidence):
    """Kiểm tra 1 lần (không lặp/chờ) xem có ảnh nào trong danh sách đang
    xuất hiện trên màn hình không. Dùng để phát hiện trạng thái "đã chọn"
    (skip_if_images) mà không tốn thời gian chờ timeout."""
    for image_name in image_names:
        location, warning = _locate_candidate(image_name, region, confidence)
        if warning:
            print(warning)
        if location is not None:
            return True, image_name
    return False, None


def find_and_click(image_names, region, confidence, timeout, optional=False):
    """Tìm nút theo 1 hoặc nhiều ảnh mẫu ứng viên trong vùng cửa sổ game rồi
    click vào giữa ảnh khớp trước tiên. Trả về True nếu click được, False
    nếu không ảnh nào khớp trong thời gian chờ."""
    if isinstance(image_names, str):
        image_names = [image_names]

    deadline = time.time() + timeout
    warned = set()
    while time.time() < deadline:
        for image_name in image_names:
            location, warning = _locate_candidate(image_name, region, confidence)
            if warning and image_name not in warned:
                print(warning)
                warned.add(image_name)

            if location is not None:
                pyautogui.moveTo(location.x, location.y, duration=MOVE_DURATION)
                pyautogui.click()
                print(f"✅ Click '{image_name}' tại ({location.x}, {location.y})")
                return True

        time.sleep(FIND_INTERVAL)

    label = " / ".join(image_names)
    if optional:
        print(f"⏭️  '{label}' không xuất hiện (có thể đã chọn rồi) -> bỏ qua")
    else:
        print(f"❌ Không tìm thấy nút '{label}' sau {timeout}s, bỏ qua bước này.")
        _save_debug_screenshot(image_names[0], region)
    return False


def _save_debug_screenshot(image_name, region):
    """Lưu ảnh chụp đúng vùng đang tìm kiếm để so sánh trực tiếp với ảnh mẫu,
    giúp chẩn đoán lý do không khớp (lệch vị trí, độ phân giải, màu sắc...)."""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        shot = pyautogui.screenshot(region=region)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(image_name)[0]
        debug_path = os.path.join(DEBUG_DIR, f"missed_{base_name}_{stamp}.png")
        shot.save(debug_path)
        print(f"🖼️  Đã lưu ảnh debug: {debug_path}")
    except Exception as e:
        print(f"⚠️  Không lưu được ảnh debug: {e}")


def click_at_center_offset(win, dx, dy, name):
    """Click theo toạ độ = tâm cửa sổ + offset (dx, dy). Dùng cho nút bị
    khuất/che nên không thể nhận diện bằng ảnh. Offset theo tâm (thay vì góc
    trái/trên) vẫn đúng khi cửa sổ đổi kích thước, vì popup trong game luôn
    canh giữa màn hình."""
    if dx is None or dy is None:
        print(f"⚠️  Chưa cấu hình toạ độ cho '{name}' (dùng show_mouse_pos.py để lấy dx, dy).")
        return False

    abs_x = round(win.left + win.width / 2 + dx)
    abs_y = round(win.top + win.height / 2 + dy)
    pyautogui.moveTo(abs_x, abs_y, duration=MOVE_DURATION)
    pyautogui.click()
    print(f"✅ Click toạ độ '{name}' tại ({abs_x}, {abs_y})")
    return True


def _orange_mask(bgr):
    return cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), SELECTED_ORANGE_LOW, SELECTED_ORANGE_HIGH)


def _best_match(frame_gray, image_name, confidence):
    """Khớp 1 ảnh mẫu trên khung hình xám. Trả về (điểm, x, y, ảnh mẫu BGR)
    nếu điểm >= confidence, ngược lại None."""
    path = os.path.join(BUTTON_DIR, image_name)
    tpl = cv2.imread(path)
    if tpl is None:
        print(f"⚠️  Thiếu ảnh mẫu: {path}")
        return None
    th, tw = tpl.shape[:2]
    if th > frame_gray.shape[0] or tw > frame_gray.shape[1]:
        return None
    res = cv2.matchTemplate(frame_gray, cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY), cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(res)
    return (score, x, y, tpl) if score >= confidence else None


def find_card(region, images, selected_images, confidence):
    """Tìm card mục tiêu 1 lần. Trả về ("selected", None) nếu thấy card ĐÃ chọn,
    ("click", (x, y)) nếu thấy card chưa chọn (toạ độ tâm để click), hoặc
    ("none", None). Trạng thái "đã chọn" xác định bằng khung góc cam."""
    left, top, _, _ = region
    shot = pyautogui.screenshot(region=region)
    frame = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame_orange = cv2.dilate(_orange_mask(frame), np.ones((5, 5), np.uint8))

    # 1) Đã chọn? Ảnh "đã chọn" phải khớp VÀ khung cam của ảnh mẫu phải có mặt
    #    trên màn hình (card chưa chọn cũng khớp ảnh này ~0.92 nhưng không có cam).
    best_click = None
    for name in selected_images:
        m = _best_match(gray, name, confidence)
        if m is None:
            continue
        score, x, y, tpl = m
        ref = _orange_mask(tpl) > 0
        ref_n = int(ref.sum())
        if ref_n == 0:
            continue
        h, w = ref.shape
        yy, xx = np.where(ref)
        # frame_orange đã giãn 2px mỗi phía ở trên -> chịu lệch pixel nhỏ.
        hit = int(np.count_nonzero(frame_orange[y + yy, x + xx]))
        fraction = hit / ref_n
        print(f"🔎 '{name}' khớp {score:.2f}, khung cam {fraction:.0%}")
        if fraction >= SELECTED_MIN_FRACTION:
            return "selected", None
        if best_click is None or score > best_click[0]:
            best_click = (score, left + x + w / 2, top + y + h / 2)

    # 2) Chưa chọn -> tìm card để click.
    for name in images:
        m = _best_match(gray, name, confidence)
        if m is None:
            continue
        score, x, y, tpl = m
        if best_click is None or score > best_click[0]:
            best_click = (score, left + x + tpl.shape[1] / 2, top + y + tpl.shape[0] / 2)
        print(f"🔎 '{name}' khớp {score:.2f}")

    if best_click is None:
        return "none", None
    return "click", (round(best_click[1]), round(best_click[2]))


def select_card(btn, region):
    """Đảm bảo card mục tiêu đang được chọn. Trả về (đã_xong, đã_click):
    đã_xong=True khi card đã chọn sẵn hoặc vừa click; False nếu không thấy card
    trong thời gian chờ (khi đó KHÔNG đánh dấu once, lần sau thử lại)."""
    deadline = time.time() + btn["timeout"]
    while True:
        state, pos = find_card(region, btn["images"], btn["selected_images"], btn["confidence"])
        if state == "selected":
            print("⏭️  Card mục tiêu đã được chọn -> bỏ qua")
            return True, False
        if state == "click":
            pyautogui.moveTo(pos[0], pos[1], duration=MOVE_DURATION)
            pyautogui.click()
            print(f"✅ Click card mục tiêu tại {pos}")
            return True, True
        if time.time() >= deadline:
            print(f"❌ Không thấy card mục tiêu sau {btn['timeout']}s")
            _save_debug_screenshot(btn["images"][0], region)
            return False, False
        time.sleep(FIND_INTERVAL)


def run_boss_sequence(win, region):
    for btn in BUTTONS:
        once = btn.get("once")
        name = btn.get("name")

        # Bước "once": chỉ kiểm tra/click đúng 1 lần xuyên suốt cả quá trình
        # chạy. Từ lần thứ 2 trở đi bỏ qua ngay, không tốn thời gian tìm ảnh.
        if once and name in _clicked_once:
            continue

        if btn["type"] == "select_card":
            done, clicked = select_card(btn, region)
            # Chỉ đánh dấu "xong" khi thực sự đã chọn/đã click; không thấy card
            # thì để lần sau thử lại thay vì bỏ qua vĩnh viễn.
            if once and done:
                _clicked_once.add(name)
            if clicked:
                time.sleep(btn["delay"])
            continue

        if btn["type"] == "coord":
            clicked = click_at_center_offset(win, btn["dx"], btn["dy"], name)
        else:
            skip_images = btn.get("skip_if_images")
            if skip_images:
                already_done, matched = any_image_present(skip_images, region, btn["confidence"])
                if already_done:
                    print(f"⏭️  '{matched}' đang hiển thị (đã chọn rồi) -> bỏ qua bước này")
                    if once:
                        _clicked_once.add(name)
                    continue

            image_names = btn.get("images") or [btn["image"]]
            clicked = find_and_click(
                image_names, region, btn["confidence"], btn["timeout"], optional=btn["optional"]
            )

        # Với bước once + optional: dù có click được hay không, lần kiểm tra
        # đầu tiên đã đủ để kết luận (đã chọn từ trước hoặc vừa mới chọn)
        # nên đánh dấu xong, không cần kiểm tra lại các lần sau.
        if once:
            _clicked_once.add(name)

        if clicked:
            time.sleep(btn["delay"])


def run_sequence_bot():
    window_title = 'Top Heroes'

    try:
        # Tìm cửa sổ game. Có thể có nhiều cửa sổ/tooltip trùng tên, nên lấy
        # cửa sổ có diện tích lớn nhất thay vì luôn lấy phần tử đầu tiên.
        wins = gw.getWindowsWithTitle(window_title)
        if not wins:
            raise IndexError
        win = max(wins, key=lambda w: w.width * w.height)

        if win.isMinimized:
            win.restore()

        win.activate()
        time.sleep(1)

        print(f"🪟 Cửa sổ game (raw): left={win.left}, top={win.top}, width={win.width}, height={win.height}")
        print(f"🔍 Vùng tìm kiếm (đã kẹp >=0): {get_search_region(win)}")
        print(f"🚀 Bot đang chạy chuỗi {len(BUTTONS)} bước (nhận diện theo ảnh nút) trên Desktop ảo.")
        print(f"🔁 Còn đội 'Idle' thì tự đánh tiếp, kiểm tra mỗi {IDLE_CHECK_INTERVAL}s.")
        print("💡 Nhấn Ctrl + C để dừng. Hãy chuyển sang Desktop khác để làm việc.")

        while True:
            # Giới hạn vùng tìm kiếm trong cửa sổ game: nhanh hơn và tránh nhận
            # nhầm ảnh giống nút ở ngoài cửa sổ game. Tính lại mỗi vòng phòng
            # khi cửa sổ bị di chuyển/resize.
            region = get_search_region(win)

            has_idle, _matched = any_image_present(IDLE_IMAGES, region, IDLE_CONFIDENCE)
            if has_idle:
                pyautogui.press('esc')
                run_boss_sequence(win, region)
                pyautogui.press('esc')
            else:
                print("⏸️  Không còn đội Idle, chờ...", end="\r")

            time.sleep(IDLE_CHECK_INTERVAL)

    except IndexError:
        print(f"❌ Không tìm thấy cửa sổ: {window_title}")
        input("\nNhấn Enter để đóng...")
    except KeyboardInterrupt:
        print("\n🛑 Bot đã dừng bởi người dùng.")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        input("\nNhấn Enter để đóng...")


if __name__ == "__main__":
    run_sequence_bot()
