import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
import ctypes
import time
import mss

ctypes.windll.shcore.SetProcessDpiAwareness(1)

# ═══════════════════════════════════════════════════════════
#  CẤU HÌNH - Chỉnh tại đây
# ═══════════════════════════════════════════════════════════
WINDOW_TITLE   = "Top Heroes"  # Tên cửa sổ game

# Vùng mini-game BÊN TRONG cửa sổ Top Heroes (pixel tương đối)
# Bạn cần đo vùng mini-game thực tế, ví dụ:
GAME_REGION = {
    "left_offset": 540,
    "top_offset":  50,
    "width":       466,
    "height":      835,
}
BIRD_X_RATIO   = 0.25    # Chim thường ở khoảng 25% chiều rộng vùng game
SCAN_X_RATIO   = 0.6    # Quét cột tại 50% (phía trước chim)
JUMP_THRESHOLD = 40      # Chim thấp hơn tâm khoảng trống N px thì nhảy
LOOP_INTERVAL  = 0.03    # ~30 lần/giây
DEBUG          = True     # Hiện cửa sổ debug để canh chỉnh
# ═══════════════════════════════════════════════════════════


def get_window():
    wins = gw.getWindowsWithTitle(WINDOW_TITLE)
    if not wins:
        raise RuntimeError(f"❌ Không tìm thấy cửa sổ: '{WINDOW_TITLE}'")
    win = wins[0]
    if win.isMinimized:
        win.restore()
    win.activate()
    time.sleep(0.5)
    return win


def capture_game_region(win):
    """Chụp đúng vùng mini-game bên trong cửa sổ Top Heroes."""
    with mss.mss() as sct:
        region = {
            "left":   win.left + GAME_REGION["left_offset"],
            "top":    win.top  + GAME_REGION["top_offset"],
            "width":  GAME_REGION["width"],
            "height": GAME_REGION["height"],
        }
        shot = sct.grab(region)
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)


def find_gap_and_bird(frame):
    h, w = frame.shape[:2]
    scan_x = int(w * SCAN_X_RATIO)
    bird_x = int(w * BIRD_X_RATIO)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # ── 1. Tìm cột xám ─────────────────────────────────────
    # Cột màu xám xanh rêu → saturation thấp, value trung bình
    lower_col = np.array([90,  10,  80])
    upper_col = np.array([140, 80, 180])
    mask_col  = cv2.inRange(hsv, lower_col, upper_col)

    # Chỉ xét vùng trung tâm (bỏ UI trên/dưới 8%)
    margin_top = int(h * 0.08)
    margin_bot = int(h * 0.92)
    mask_col[:margin_top, :] = 0
    mask_col[margin_bot:, :] = 0

    # Quét cột dọc tại scan_x → tìm vùng KHÔNG có cột = gap
    col = mask_col[:, scan_x]
    is_col = col > 0

    gap_top = gap_bot = gap_center = None
    best_size = 0
    i = margin_top
    while i < margin_bot:
        if not is_col[i]:
            start = i
            while i < margin_bot and not is_col[i]:
                i += 1
            size = i - start
            if size > best_size and size < h * 0.8:
                best_size = size
                gap_top = start
                gap_bot = i
        else:
            i += 1

    if gap_top is not None:
        gap_center = (gap_top + gap_bot) // 2

    # ── 2. Tìm con cá (cam + trắng) ───────────────────────
    # Mở rộng dải cam
    lower_fish = np.array([0,  80, 150])
    upper_fish = np.array([30, 255, 255])
    mask_fish  = cv2.inRange(hsv, lower_fish, upper_fish)

    # Chỉ tìm trong nửa trái màn hình (khu vực cá bơi)
    mask_fish[:, int(w*0.6):] = 0
    mask_fish[:margin_top, :] = 0

    ys = np.where(mask_fish > 0)
    if len(ys[0]) > 0:
        bird_y = int(np.mean(ys[0]))
        bird_x = int(np.mean(ys[1]))  # Cập nhật bird_x theo vị trí thực
    else:
        bird_y = h // 2

    return gap_center, bird_y, scan_x, bird_x, gap_top, gap_bot


def do_jump(win):
    """Click vào vùng mini-game để nhảy."""
    click_x = win.left + GAME_REGION["left_offset"] + GAME_REGION["width"]  // 2
    click_y = win.top  + GAME_REGION["top_offset"]  + GAME_REGION["height"] // 2
    pyautogui.click(click_x, click_y)


def run_bot():
    print("🔍 Đang tìm cửa sổ game...")
    win = get_window()
    print(f"✅ Tìm thấy: {win.title}  |  Pos: ({win.left}, {win.top})  Size: {win.width}x{win.height}")
    print("🚀 Bot đang chạy. Nhấn Ctrl+C để dừng.\n")
    
    # ── Tự động click giữa vùng mini-game để Start ────────
    start_x = win.left + GAME_REGION["left_offset"] + GAME_REGION["width"]  // 2
    start_y = win.top  + GAME_REGION["top_offset"]  + GAME_REGION["height"] // 2
    print(f"🖱️  Click start tại ({start_x}, {start_y})...")
    time.sleep(1)  # Chờ cửa sổ focus xong

    
    # ── Hover 2s đầu: click đều để giữ chim không rơi ─────
    print("⏳ Đang giữ chim lơ lửng...")
    hover_duration = 1   # Giây hover trước khi nhận diện
    hover_interval = 0.5  # Click mỗi 0.5s = 2 lần/giây
    hover_end = time.time() + hover_duration
    while time.time() < hover_end:
        pyautogui.click(start_x, start_y)
        time.sleep(hover_interval)

    last_jump_time = 0
    JUMP_COOLDOWN  = 0.25   # Giây - tránh nhảy liên tục

    while True:
        try:
            frame = capture_game_region(win)
            gap_center, bird_y, scan_x, bird_x, gap_top, gap_bot = find_gap_and_bird(frame)

            should_jump = False
            if gap_center is not None:
                diff = bird_y - gap_center   # Dương = chim thấp hơn tâm gap
                if diff > JUMP_THRESHOLD:
                    now = time.time()
                    if now - last_jump_time > JUMP_COOLDOWN:
                        do_jump(win)
                        last_jump_time = now
                        should_jump = True
                        print(f"🐦 JUMP! bird_y={bird_y} | gap_center={gap_center} | diff={diff:+d}px")

            # ── Debug visualization ────────────────────────
            if DEBUG:
                dbg = frame.copy()
                h, w = dbg.shape[:2]

                # Vẽ đường scan
                cv2.line(dbg, (scan_x, 0), (scan_x, h), (0, 255, 255), 1)
                cv2.line(dbg, (bird_x, 0), (bird_x, h), (255, 200, 0), 1)

                # Vẽ gap
                if gap_top is not None:
                    cv2.rectangle(dbg, (scan_x-10, gap_top), (scan_x+10, gap_bot), (0, 255, 0), 2)
                    cv2.line(dbg, (0, gap_center), (w, gap_center), (0, 200, 0), 1)

                # Vẽ vị trí chim
                cv2.circle(dbg, (bird_x, bird_y), 8, (0, 100, 255), -1)

                # Nhãn
                status = "JUMP!" if should_jump else "hold"
                cv2.putText(dbg, status, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0,0,255) if should_jump else (200,200,200), 2)

                cv2.imshow("Bot Debug - Top Heroes", dbg)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            time.sleep(LOOP_INTERVAL)

        except KeyboardInterrupt:
            print("\n🛑 Bot dừng.")
            break
        except Exception as e:
            print(f"❌ Lỗi: {e}")
            time.sleep(0.5)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_bot()