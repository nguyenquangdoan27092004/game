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
    # button_6.png có phần đồng hồ đếm ngược dưới chữ "Go" luôn thay đổi nên
    # không bao giờ khớp 100% với ảnh mẫu -> hạ confidence để chấp nhận sai
    # lệch ở vùng số, phần chữ "Go" + khung + icon đồng hồ vẫn phải khớp.
    {"type": "image", "image": "button_6.png", "delay": 0.25, "confidence": 0.7, "optional": False, "timeout": 5},
]

# Nút "Attack" hiện ra sau khi click đúng quái. Nếu quái đã bị chiếm thì game
# chỉ hiện dòng thông báo, không có nút này -> coi như quái không đánh được.
ATTACK_IMAGE = "button_5.png"
ATTACK_CONFIDENCE = 0.85
ATTACK_PROBE_TIMEOUT = 1.5  # giây chờ nút Attack sau khi click quái

# --- TÌM QUÁI TRÊN BẢN ĐỒ ---
# Nhận diện nhãn "Lv 1" (chữ vàng viền nâu, đứng yên dù quái vẫy cánh) bằng
# cách so khớp trên MẶT NẠ MÀU VÀNG, không phụ thuộc nền cỏ/cánh/mây. Template
# được nối thêm khoảng trống bên phải để "Lv 10", "Lv 40"... không khớp nhầm.
# lv1.png = "Lv. 1" (có chấm, đã xoá nền); lv1_nodot.png = "Lv 1" (không chấm).
LV_IMAGES = ["lv1.png", "lv1_nodot.png"]
LV_BLANK_PAD = 14                 # px trống thêm bên phải template
LV_DIGIT_THRESHOLD = 0.75         # ngưỡng khớp RIÊNG chữ số cuối (phân biệt "1" với 2, 3, 4...); chỉ đáng tin từ tỉ lệ ~0.7 trở lên
LV_PAD_YELLOW_MAX = 0.06          # tỉ lệ pixel vàng tối đa cho phép trong vùng trống đó
LV_YELLOW_LOW = (18, 130, 150)    # HSV: chữ nhãn H~20-22, S~150
LV_YELLOW_HIGH = (26, 255, 255)
LV_THRESHOLD = 0.65               # ngưỡng khớp mặt nạ (nhãn thật >= 0.78, nhiễu <= 0.6)
# Dải tỉ lệ thu phóng template để nhận diện ở mọi kích thước cửa sổ/zoom
# (1.0 = đúng cỡ ảnh mẫu). Bước nhỏ hơn = chính xác hơn nhưng chậm hơn.
LV_SCALE_MIN = 0.5
LV_SCALE_MAX = 2.0
LV_SCALE_STEP = 0.1
# Điểm click (theo cỡ ảnh mẫu, tự co giãn theo tỉ lệ nhãn) so với GIỮA cạnh trên của nhãn Lv (dx, dy): chỉ nhích lên trên nhãn
# một chút (vào bóng/thân quái). Click quá cao sẽ trượt khỏi quái - tăng độ lớn
# của dy (âm hơn) nếu click còn thấp, giảm nếu click quá cao.
CLICK_OFFSET = (0, -20)
# Vùng an toàn (tỉ lệ so với cửa sổ) - tránh click vào thanh UI trên/dưới/cạnh.
SAFE_MARGIN = {"left": 0.03, "right": 0.03, "top": 0.10, "bottom": 0.18}

# Chẩn đoán: khi quét không thấy quái, lưu ảnh màn hình có khoanh các ứng viên
# gần đúng nhất (kèm điểm khớp, tỉ lệ và lý do bị loại) vào debug/ để biết bot
# trượt vì đâu (không thấy nhãn / điểm thấp / bị bộ lọc loại).
DEBUG_SAVE_SCANS = True
DEBUG_MIN_INTERVAL = 8   # giây tối thiểu giữa 2 lần lưu
DEBUG_MAX_FILES = 30     # chỉ giữ chừng này ảnh mới nhất

# --- LƯỚT BẢN ĐỒ KHI KHÔNG CÓ QUÁI ---
# Kéo bản đồ theo zig-zag (SCAN_COLS x SCAN_ROWS màn hình) rồi đi ngược đúng
# đường cũ về điểm xuất phát, lặp mãi -> không bao giờ lạc ra rìa bản đồ.
SCAN_COLS = 4
SCAN_ROWS = 3
DRAG_RATIO_X = 0.55   # mỗi lần kéo = tỉ lệ chiều rộng cửa sổ
DRAG_RATIO_Y = 0.45   # ... tỉ lệ chiều cao cửa sổ
DRAG_DURATION = 0.35  # giây giữ chuột khi kéo
MAP_SETTLE = 0.8      # giây chờ bản đồ ổn định sau khi kéo

# Nhớ quái đã xử lý theo toạ độ BẢN ĐỒ (đã trừ độ dịch do kéo map) để không
# tìm lại: quái vừa tấn công vẫn đứng yên trên map trong lúc đội đang đánh.
ATTACKED_TTL = 240      # giây bỏ qua quái đã bấm Go (tăng nếu trận đánh lâu hơn)
OCCUPIED_TTL = 60       # giây bỏ qua quái không có nút Attack (đang bị chiếm)
BLOCK_RADIUS = 45       # px: 2 điểm gần hơn mức này coi là cùng 1 quái
PAN_TRACK_MIN_RESPONSE = 0.1  # độ tin cậy tối thiểu khi đo độ dịch thực của map

ESC_SETTLE = 0.3  # giây chờ popup đóng sau khi nhấn Esc

# Click quái trên bản đồ: game thường bỏ qua click tức thì (chuột "nhảy" tới
# rồi nhấn-nhả trong vài ms), nên phải di chuột tới, dừng một nhịp cho game
# nhận hover, rồi nhấn giữ một chút. Tăng các giá trị nếu game vẫn không phản hồi.
MAP_CLICK_APPROACH = 0.15  # giây di chuột vào điểm click
MAP_CLICK_HOVER = 0.15     # giây dừng trên quái trước khi nhấn
MAP_CLICK_HOLD = 0.12      # giây giữ chuột khi nhấn

# Ảnh chữ "Idle" trong ô Queue - dùng để biết còn đội rảnh hay không.
# Chụp bằng: python capture_button.py idle.png (khoanh sát chữ "Idle").
IDLE_IMAGES = ["idle.png"]
IDLE_CONFIDENCE = 0.85
IDLE_CHECK_INTERVAL = 0.5  # giây giữa mỗi lần kiểm tra còn đội Idle hay không

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


def _yellow_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, LV_YELLOW_LOW, LV_YELLOW_HIGH)


_lv_templates = None
_last_scale = None  # tỉ lệ nhãn tìm thấy lần trước -> lần sau dò quanh nó trước


def _digit_start(mask):
    """Cột bắt đầu của chữ số cuối trong mặt nạ nhãn (cụm cột vàng liền nhau
    ngoài cùng bên phải, ngăn cách với phần chữ trước nó bằng cột trống)."""
    cols = np.count_nonzero(mask, axis=0) > 0
    x = len(cols) - 1
    while x >= 0 and not cols[x]:
        x -= 1
    while x >= 0 and cols[x]:
        x -= 1
    return x + 1


def _get_lv_templates():
    """Đọc các ảnh nhãn Lv (hỗ trợ PNG nền trong suốt) -> mặt nạ vàng (chưa thu phóng). Ảnh thiếu thì bỏ qua."""
    global _lv_templates
    if _lv_templates is None:
        _lv_templates = []
        for name in LV_IMAGES:
            path = os.path.join(BUTTON_DIR, name)
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None:
                print(f"⚠️  Thiếu ảnh mẫu nhãn Lv: {path}")
                continue
            mask = _yellow_mask(img[:, :, :3])
            if img.shape[2] == 4:
                mask[img[:, :, 3] < 128] = 0  # pixel nền trong suốt -> không tính
            _lv_templates.append((mask, _digit_start(mask)))
        if not _lv_templates:
            raise FileNotFoundError(f"Không có ảnh mẫu nhãn Lv nào trong {BUTTON_DIR}")
    return _lv_templates


def _digit_score(mask, digit_tpl, dx, dy):
    """Điểm khớp RIÊNG của chữ số cuối: "Lv" chiếm phần lớn điểm của cả nhãn nên
    nhãn "Lv 2", "Lv 5"... vẫn khớp cao - phải kiểm tra riêng chữ số. Tìm trong
    vùng lân cận +-2px quanh vị trí kỳ vọng để chịu sai lệch do thu phóng."""
    h, w = digit_tpl.shape
    m = 2
    y0, x0 = max(0, dy - m), max(0, dx - m)
    crop = mask[y0:dy + h + m, x0:dx + w + m]
    if crop.shape[0] < h or crop.shape[1] < w or np.count_nonzero(digit_tpl) == 0:
        return 0.0
    return float(cv2.matchTemplate(crop, digit_tpl, cv2.TM_CCOEFF_NORMED).max())


def _match_labels(mask, scales):
    """So khớp mọi template ở các tỉ lệ cho trước. Trả về danh sách
    (x, y, rộng nhãn, tỉ lệ, điểm) đã NMS, chỉ giữ tỉ lệ khớp tốt nhất."""
    matches = []  # (điểm, x, y, rộng nhãn, cao nhãn, tỉ lệ)
    for base, digit_x0 in _get_lv_templates():
        for scale in scales:
            label_w = max(3, round(base.shape[1] * scale))
            label_h = max(3, round(base.shape[0] * scale))
            pad_w = round(LV_BLANK_PAD * scale)
            # INTER_AREA giữ nét chữ khi thu nhỏ.
            tpl = cv2.resize(base, (label_w, label_h), interpolation=cv2.INTER_AREA)
            tpl = np.hstack([tpl, np.zeros((label_h, pad_w), np.uint8)])
            if mask.shape[0] < tpl.shape[0] or mask.shape[1] < tpl.shape[1]:
                continue
            score = cv2.matchTemplate(mask, tpl, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(score >= LV_THRESHOLD)
            # Chữ số thừa bên phải ("Lv 10", "Lv 40"...) -> loại: vùng trống sau
            # chữ phải gần như không có pixel vàng.
            max_pad_yellow = LV_PAD_YELLOW_MAX * np.count_nonzero(base) * scale * scale
            # Phần chữ số cuối của template (đã thu phóng) để kiểm tra riêng.
            d0 = min(label_w - 2, round(digit_x0 * scale))
            digit_tpl = tpl[:, d0:label_w]
            for x, y in zip(xs, ys):
                pad_area = mask[y:y + label_h, x + label_w:x + label_w + pad_w]
                if np.count_nonzero(pad_area) > max_pad_yellow:
                    continue
                if _digit_score(mask, digit_tpl, x + d0, y) < LV_DIGIT_THRESHOLD:
                    continue
                matches.append((score[y, x], x, y, label_w, label_h, scale))

    if not matches:
        return []

    # Mọi nhãn trong cùng 1 khung hình có CÙNG tỉ lệ -> chọn tỉ lệ có điểm khớp
    # cao nhất làm chuẩn, chỉ giữ khớp ở tỉ lệ đó (và các bước kề). Nhờ vậy
    # template cỡ nhỏ không khớp nhầm vào mảng vàng (lâu đài, hiệu ứng...).
    best_scale = max(matches, key=lambda m: m[0])[5]
    matches = [m for m in matches if abs(m[5] - best_scale) <= LV_SCALE_STEP * 1.01]

    # NMS qua các tỉ lệ/template: giữ khớp tốt nhất, bỏ khớp trùng vùng.
    matches.sort(key=lambda m: -m[0])
    kept = []
    for sc, x, y, label_w, label_h, scale in matches:
        if all(abs(x - kx) > kw or abs(y - ky) > label_h for kx, ky, kw, _, _ in kept):
            kept.append((x, y, label_w, scale, sc))
    return kept


_last_debug_save = 0.0


def _save_scan_debug(frame, mask, region):
    """Lưu ảnh chẩn đoán: khoanh 6 ứng viên có điểm khớp THÔ cao nhất (kể cả
    những cái bị loại) + ảnh mặt nạ vàng. Mỗi ô ghi: điểm/tỉ lệ/lý do."""
    global _last_debug_save
    now = time.time()
    if now - _last_debug_save < DEBUG_MIN_INTERVAL:
        return
    _last_debug_save = now

    cands = []  # (điểm, x, y, w, h, tỉ lệ, lý do)
    for base, _digit_x0 in _get_lv_templates():
        for scale in np.arange(LV_SCALE_MIN, LV_SCALE_MAX + 1e-9, LV_SCALE_STEP):
            lw = max(3, round(base.shape[1] * scale))
            lh = max(3, round(base.shape[0] * scale))
            pw = round(LV_BLANK_PAD * scale)
            tpl = cv2.resize(base, (lw, lh), interpolation=cv2.INTER_AREA)
            tpl = np.hstack([tpl, np.zeros((lh, pw), np.uint8)])
            if mask.shape[0] < tpl.shape[0] or mask.shape[1] < tpl.shape[1]:
                continue
            sc = cv2.matchTemplate(mask, tpl, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(sc)
            x, y = loc
            pad_n = np.count_nonzero(mask[y:y + lh, x + lw:x + lw + pw])
            pad_max = LV_PAD_YELLOW_MAX * np.count_nonzero(base) * scale * scale
            reason = "diem thap" if mx < LV_THRESHOLD else ("du chu so" if pad_n > pad_max else "ok")
            cands.append((mx, x, y, lw, lh, scale, reason))
    cands.sort(key=lambda c: -c[0])
    shown = []
    for c in cands:
        if all(abs(c[1] - o[1]) > 20 or abs(c[2] - o[2]) > 20 for o in shown):
            shown.append(c)
        if len(shown) >= 6:
            break

    vis = frame.copy()
    for mx, x, y, lw, lh, scale, reason in shown:
        color = (0, 200, 0) if reason == "ok" else (0, 0, 255)
        cv2.rectangle(vis, (x, y), (x + lw, y + lh), color, 2)
        cv2.putText(vis, f"{mx:.2f} s{scale:.1f} {reason}", (x, max(12, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(os.path.join(DEBUG_DIR, f"scan_{stamp}_annotated.png"), vis)
        cv2.imwrite(os.path.join(DEBUG_DIR, f"scan_{stamp}_raw.png"), frame)
        cv2.imwrite(os.path.join(DEBUG_DIR, f"scan_{stamp}_mask.png"), mask_bgr)
        old = sorted(f for f in os.listdir(DEBUG_DIR) if f.startswith("scan_"))
        for f in old[:-DEBUG_MAX_FILES * 3]:
            os.remove(os.path.join(DEBUG_DIR, f))
        best = shown[0] if shown else None
        info = f"điểm cao nhất {best[0]:.2f} ({best[6]})" if best else "không có ứng viên"
        print(f"🖼️  Không thấy quái - đã lưu ảnh chẩn đoán scan_{stamp}_*.png, {info}")
    except Exception as e:
        print(f"⚠️  Không lưu được ảnh chẩn đoán: {e}")


def find_monsters(region):
    """Trả về danh sách điểm click (toạ độ màn hình tuyệt đối) của các quái Lv 1
    đang hiển thị, sắp theo khoảng cách tới tâm vùng (gần tâm trước)."""
    left, top, width, height = region
    shot = pyautogui.screenshot(region=region)
    frame = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    mask = _yellow_mask(frame)
    global _last_scale
    all_scales = np.arange(LV_SCALE_MIN, LV_SCALE_MAX + 1e-9, LV_SCALE_STEP)
    # Đã biết tỉ lệ lần trước -> thử dải hẹp quanh nó (nhanh hơn nhiều); không
    # thấy gì thì quay lại dò toàn dải (VD: người dùng vừa đổi cỡ cửa sổ).
    if _last_scale is not None:
        near = all_scales[np.abs(all_scales - _last_scale) <= LV_SCALE_STEP * 2.01]
        attempts = [near, all_scales]
    else:
        attempts = [all_scales]

    kept = []
    for scales in attempts:
        kept = _match_labels(mask, scales)
        if kept:
            _last_scale = max(kept, key=lambda k: k[4])[3]
            break

    safe_l = left + width * SAFE_MARGIN["left"]
    safe_r = left + width * (1 - SAFE_MARGIN["right"])
    safe_t = top + height * SAFE_MARGIN["top"]
    safe_b = top + height * (1 - SAFE_MARGIN["bottom"])

    points = []
    for x, y, label_w, scale, _ in kept:
        # Offset click cũng co giãn theo tỉ lệ nhãn tìm thấy.
        cx = left + x + label_w / 2 + CLICK_OFFSET[0] * scale
        cy = top + y + CLICK_OFFSET[1] * scale
        if safe_l <= cx <= safe_r and safe_t <= cy <= safe_b:
            points.append((round(cx), round(cy)))

    if not points and DEBUG_SAVE_SCANS:
        _save_scan_debug(frame, mask, region)

    mid_x, mid_y = left + width / 2, top + height / 2
    points.sort(key=lambda p: (p[0] - mid_x) ** 2 + (p[1] - mid_y) ** 2)
    return points


class MapScanner:
    """Sinh các bước kéo bản đồ: zig-zag đi hết lưới rồi đi ngược đường cũ về
    điểm xuất phát, lặp vô hạn. Mỗi bước là (dx, dy) hướng "xem" bản đồ."""

    def __init__(self, cols=SCAN_COLS, rows=SCAN_ROWS):
        forward = []
        direction = 1
        for r in range(rows):
            forward += [(direction, 0)] * (cols - 1)
            if r < rows - 1:
                forward.append((0, 1))
            direction = -direction
        back = [(-dx, -dy) for dx, dy in reversed(forward)]
        self.cycle = forward + back
        self.i = 0

    def next_move(self):
        move = self.cycle[self.i]
        self.i = (self.i + 1) % len(self.cycle)
        return move


def pan_map(win, view_dx, view_dy):
    """Dịch vùng xem bản đồ (view_dx, view_dy) bước bằng cách kéo chuột NGƯỢC
    hướng (kéo trái = xem sang phải). Điểm kéo đối xứng quanh tâm cửa sổ để
    không chạm ra ngoài."""
    cx = win.left + win.width / 2
    cy = win.top + win.height / 2
    step_x = win.width * DRAG_RATIO_X
    step_y = win.height * DRAG_RATIO_Y
    sx = cx + view_dx * step_x / 2
    sy = cy + view_dy * step_y / 2
    ex = sx - view_dx * step_x
    ey = sy - view_dy * step_y
    region = get_search_region(win)
    before = _grab_gray(region)
    pyautogui.moveTo(sx, sy, duration=MAP_CLICK_APPROACH)
    time.sleep(MAP_CLICK_HOVER)
    pyautogui.mouseDown()
    time.sleep(MAP_CLICK_HOLD)
    pyautogui.moveTo(ex, ey, duration=DRAG_DURATION)
    pyautogui.mouseUp()
    time.sleep(MAP_SETTLE)

    # Cập nhật offset bản đồ bằng độ dịch THỰC (kéo chuột có thể không dịch đúng
    # khoảng cách mong muốn); đo không được thì dùng khoảng cách kéo danh nghĩa.
    shift = _measure_shift(before, _grab_gray(region))
    if shift is None:
        shift = (ex - sx, ey - sy)
    # Nội dung dịch (+dx) trên màn hình => offset giảm dx.
    _view_offset[0] -= shift[0]
    _view_offset[1] -= shift[1]


_view_offset = [0.0, 0.0]  # toạ độ bản đồ = toạ độ màn hình + offset này
_blocked = []               # (world_x, world_y, hết hạn lúc) quái cần bỏ qua


def _grab_gray(region):
    shot = pyautogui.screenshot(region=region)
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2GRAY).astype(np.float32)


def _measure_shift(before, after):
    """Độ dịch (dx, dy) của nội dung màn hình giữa 2 ảnh, hoặc None nếu 2 ảnh
    không đủ giống nhau để đo (VD: bản đồ chưa tải xong)."""
    if before.shape != after.shape:
        return None
    window = cv2.createHanningWindow((before.shape[1], before.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(before, after, window)
    if response < PAN_TRACK_MIN_RESPONSE:
        return None
    return dx, dy


def block_monster(x, y, ttl):
    """Đánh dấu quái tại điểm màn hình (x, y) là cần bỏ qua trong ttl giây."""
    wx, wy = x + _view_offset[0], y + _view_offset[1]
    _blocked.append((wx, wy, time.time() + ttl))


def is_blocked(x, y):
    now = time.time()
    _blocked[:] = [b for b in _blocked if b[2] > now]
    wx, wy = x + _view_offset[0], y + _view_offset[1]
    return any(abs(wx - bx) <= BLOCK_RADIUS and abs(wy - by) <= BLOCK_RADIUS
               for bx, by, _ in _blocked)


def click_map(x, y):
    """Click 1 điểm trên bản đồ theo kiểu "người thật": đi tới từ gần đó, dừng,
    nhấn giữ rồi nhả mà KHÔNG di chuyển (di chuyển khi nhấn sẽ bị tính là kéo
    bản đồ chứ không phải click)."""
    pyautogui.moveTo(x - 25, y - 15)
    pyautogui.moveTo(x, y, duration=MAP_CLICK_APPROACH)
    time.sleep(MAP_CLICK_HOVER)
    pyautogui.mouseDown()
    time.sleep(MAP_CLICK_HOLD)
    pyautogui.mouseUp()


def hunt_monster(win, scanner):
    """Tìm và tấn công 1 quái: quét màn hình, không có thì kéo map sang vùng
    kế. Trả về True nếu đã bấm Go, False nếu hết đội Idle giữa chừng."""
    while True:
        region = get_search_region(win)

        has_idle, _ = any_image_present(IDLE_IMAGES, region, IDLE_CONFIDENCE)
        if not has_idle:
            return False

        points = [p for p in find_monsters(region) if not is_blocked(*p)]

        for x, y in points:
            click_map(x, y)
            print(f"🎯 Click quái tại ({x}, {y})")
            if find_and_click(ATTACK_IMAGE, region, ATTACK_CONFIDENCE,
                              ATTACK_PROBE_TIMEOUT, optional=True):
                time.sleep(0.6)
                block_monster(x, y, ATTACKED_TTL)
                run_boss_sequence(win, get_search_region(win))
                pyautogui.press('esc')
                time.sleep(ESC_SETTLE)
                return True
            print("⏭️  Không có nút Attack (quái đang bị chiếm?) -> thử quái khác")
            # Click sai có thể mở popup khác -> Esc để thoát ra trước khi thử tiếp.
            pyautogui.press('esc')
            time.sleep(ESC_SETTLE)
            block_monster(x, y, OCCUPIED_TTL)

        if points:
            continue  # vừa thử hết quái trên màn hình (đã đánh dấu bỏ qua) -> quét lại trước khi kéo

        print("🗺️  Không có quái trên màn hình -> kéo bản đồ")
        pan_map(win, *scanner.next_move())


def run_boss_sequence(win, region):
    for btn in BUTTONS:
        once = btn.get("once")
        name = btn.get("name")

        # Bước "once": chỉ kiểm tra/click đúng 1 lần xuyên suốt cả quá trình
        # chạy. Từ lần thứ 2 trở đi bỏ qua ngay, không tốn thời gian tìm ảnh.
        if once and name in _clicked_once:
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
        print(f"🚀 Bot đang tìm quái Lv 1 trên bản đồ (nhận diện nhãn Lv) trên Desktop ảo.")
        print(f"🔁 Còn đội 'Idle' thì tự đánh tiếp, kiểm tra mỗi {IDLE_CHECK_INTERVAL}s.")
        print("💡 Nhấn Ctrl + C để dừng. Hãy chuyển sang Desktop khác để làm việc.")

        scanner = MapScanner()
        while True:
            # Giới hạn vùng tìm kiếm trong cửa sổ game: nhanh hơn và tránh nhận
            # nhầm ảnh giống nút ở ngoài cửa sổ game. Tính lại mỗi vòng phòng
            # khi cửa sổ bị di chuyển/resize.
            region = get_search_region(win)

            has_idle, _matched = any_image_present(IDLE_IMAGES, region, IDLE_CONFIDENCE)
            if has_idle:
                pyautogui.press('esc')
                hunt_monster(win, scanner)
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
