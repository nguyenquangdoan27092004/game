"""
Flappy Fish Auto-Bot (v2 - Edge Detection)
===========================================
Yêu cầu:
    pip install opencv-python pyautogui numpy mss

Cách dùng:
    python flappy_fish_bot.py          → chạy bot
    python flappy_fish_bot.py calibrate → kiểm tra detection

Dừng bot: Ctrl+C hoặc di chuột lên góc TRÁI TRÊN màn hình
"""

import cv2
import numpy as np
import pyautogui
import time
import mss
import sys
import ctypes

# ─────────────────────────────────────────────────────
#  CẤU HÌNH - Điền tọa độ vùng mini game của bạn
# ─────────────────────────────────────────────────────

# Điền 4 giá trị này dựa trên kết quả chạy find_coords.py
GAME_X = 681    # Tọa độ X góc trái trên
GAME_Y = 166    # Tọa độ Y góc trái trên
GAME_W = 553    # Chiều rộng vùng game
GAME_H = 729    # Chiều cao vùng game

DEBUG = True    # True = hiện cửa sổ debug; False = chạy ẩn

# Cách tinh chỉnh nếu cần:
# - CLICK_THRESHOLD: giảm xuống (0.0 → -0.2) nếu bot click quá sớm
#                    tăng lên (0.2 → 0.3) nếu bot click quá trễ
CLICK_THRESHOLD = 0.10   # Click khi cá thấp hơn gap_center + threshold*gap_size

# Giới hạn tốc độ click (giây). Giảm nếu game nhanh, tăng nếu cá vọt lên quá cao
MIN_CLICK_INTERVAL = 0.10

# ─────────────────────────────────────────────────────
#  MÀU SẮC CÁ (HSV)
# ─────────────────────────────────────────────────────
# Màu cam/đỏ của thân cá clown
FISH_LOWER = np.array([6,  140, 130])
FISH_UPPER = np.array([18, 255, 255])

# ─────────────────────────────────────────────────────
#  HÀM CHÍNH
# ─────────────────────────────────────────────────────

pyautogui.FAILSAFE = True

def capture():
    with mss.mss() as sct:
        mon = {"top": GAME_Y, "left": GAME_X, "width": GAME_W, "height": GAME_H}
        shot = sct.grab(mon)
        frame = np.array(shot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)


def find_fish(frame):
    """
    Phát hiện con cá bằng màu cam (H=6-18).
    Bỏ qua vùng UI phía trên (hearts + score icon).
    Trả về (cx, cy) hoặc None.
    """
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, FISH_LOWER, FISH_UPPER)

    # Bỏ qua 15% trên cùng (hearts, score UI)
    mask[:int(h * 0.15), :] = 0
    # Bỏ qua góc trên-phải (fish score icon)
    mask[:int(h * 0.20), w // 2:] = 0

    # Lọc nhiễu nhỏ
    kernel = np.ones((4, 4), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Lấy contour lớn nhất
    valid = [c for c in contours if cv2.contourArea(c) > 60]
    if not valid:
        return None

    # Gộp tất cả contour cá (thân + vây) để lấy trung tâm chung
    all_pts = np.vstack(valid)
    M = cv2.moments(all_pts)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy)


def find_gap(frame, fish_x):
    """
    Tìm khoảng trống (gap) giữa 2 cột phía trước con cá.
    Dùng SobelX edge density: vùng có ít cạnh ngang = khoảng trống.
    Trả về (gap_top, gap_bottom) hoặc None.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Tính Sobel X (cạnh dọc của cột trụ)
    sobelX = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobelX_abs = np.uint8(np.clip(np.absolute(sobelX), 0, 255))

    # Vùng tìm kiếm: phía trước cá, không ra ngoài frame
    search_start = max(0, fish_x + 15)
    search_end   = min(w, fish_x + int(w * 0.55))

    # Với mỗi hàng Y, đếm số cạnh trong vùng tìm kiếm
    # Hàng ít cạnh → open water → thuộc gap
    gap_rows = []
    for y in range(0, h, 2):
        density = int(np.sum(sobelX_abs[y, search_start:search_end] > 28))
        if density < 4:
            gap_rows.append(y)

    if not gap_rows:
        return None

    # Nhóm các hàng liên tiếp thành regions
    regions = []
    start = prev = gap_rows[0]
    for r in gap_rows[1:]:
        if r - prev > 18:
            regions.append((start, prev))
            start = r
        prev = r
    regions.append((start, prev))

    # Lọc: region đủ lớn, không quá sát mép trên/dưới
    margin = int(h * 0.05)
    valid = [(s, e) for s, e in regions
             if (e - s) > 40
             and s > margin
             and e < h - margin]

    if not valid:
        return None

    # Chọn region lớn nhất ở phần trên của frame (gap thực sự)
    # (tránh nhầm với đáy biển phía dưới)
    upper_half = [(s, e) for s, e in valid if (s + e) // 2 < h * 0.75]
    candidates = upper_half if upper_half else valid
    best = max(candidates, key=lambda x: x[1] - x[0])
    return best  # (gap_top_y, gap_bottom_y)


def click_game():
    """Click vào giữa vùng mini game"""
    px = GAME_X + GAME_W // 2
    py = GAME_Y + GAME_H // 2
    pyautogui.click(px, py)


def run_bot():
    print("=" * 55)
    print("  Flappy Fish Bot v2 đang chạy!")
    print(f"  Vùng game: x={GAME_X} y={GAME_Y} w={GAME_W} h={GAME_H}")
    print("  Dừng: Ctrl+C hoặc di chuột lên góc TRÁI TRÊN")
    print("=" * 55)
    print("Chuyển sang cửa sổ game trong 3 giây...")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("Bắt đầu!\n")

    last_click = 0
    frame_count = 0
    no_fish_count = 0
    no_gap_count = 0

    while True:
        try:
            frame = capture()
            fish = find_fish(frame)

            debug_frame = frame.copy() if DEBUG else None

            if fish is None:
                no_fish_count += 1
                if no_fish_count % 30 == 0:
                    print(f"  [!] Không tìm thấy cá ({no_fish_count} frame)")
            else:
                no_fish_count = 0
                fish_x, fish_y = fish
                gap = find_gap(frame, fish_x)

                if gap is None:
                    no_gap_count += 1
                else:
                    no_gap_count = 0
                    gap_top, gap_bottom = gap
                    gap_size   = gap_bottom - gap_top
                    gap_center = (gap_top + gap_bottom) // 2
                    threshold  = gap_center + gap_size * CLICK_THRESHOLD

                    if DEBUG and debug_frame is not None:
                        # Vẽ cá
                        cv2.circle(debug_frame, fish, 12, (0, 255, 0), 2)
                        # Vẽ gap
                        cv2.line(debug_frame, (0, gap_top),    (GAME_W, gap_top),    (0, 220, 220), 2)
                        cv2.line(debug_frame, (0, gap_bottom), (GAME_W, gap_bottom), (0, 220, 220), 2)
                        cv2.line(debug_frame, (0, gap_center), (GAME_W, gap_center), (0, 0, 255),   1)
                        cv2.putText(debug_frame, f"fish_y={fish_y} gap={gap_top}-{gap_bottom}",
                                    (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)

                    now = time.time()
                    if fish_y > threshold and (now - last_click) >= MIN_CLICK_INTERVAL:
                        click_game()
                        last_click = now
                        if DEBUG and debug_frame is not None:
                            cv2.putText(debug_frame, "CLICK!", (8, 55),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 2)

            if DEBUG and debug_frame is not None:
                cv2.imshow("Flappy Fish Bot", debug_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("Dừng bot (Q).")
                    break

            frame_count += 1
            time.sleep(0.028)  # ~35 FPS

        except KeyboardInterrupt:
            print("\nBot đã dừng (Ctrl+C).")
            break
        except pyautogui.FailSafeException:
            print("\nBot đã dừng (FailSafe - chuột góc trái trên).")
            break
        except Exception as e:
            print(f"Lỗi: {e}")
            time.sleep(0.1)

    if DEBUG:
        cv2.destroyAllWindows()
    print(f"Tổng frames: {frame_count}")


# ─────────────────────────────────────────────────────
#  CALIBRATE MODE
# ─────────────────────────────────────────────────────

def calibrate():
    """
    Chụp vùng game và hiển thị kết quả detection.
    Dùng để kiểm tra trước khi chạy bot thật.
    """
    print("Chế độ Calibrate")
    print("Hãy mở game đến màn hình đang chơi (có cá + cột).")
    print("Chụp sau 3 giây...")
    time.sleep(3)

    frame = capture()
    fish  = find_fish(frame)
    h, w  = frame.shape[:2]

    debug = frame.copy()

    if fish:
        fish_x, fish_y = fish
        cv2.circle(debug, fish, 15, (0, 255, 0), 3)
        cv2.putText(debug, f"Fish ({fish_x},{fish_y})",
                    (fish_x + 18, fish_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        print(f"[OK] Cá tìm thấy tại: ({fish_x}, {fish_y})")

        gap = find_gap(frame, fish_x)
        if gap:
            gt, gb = gap
            gc = (gt + gb) // 2
            cv2.line(debug, (0, gt), (w, gt), (0, 220, 220), 2)
            cv2.line(debug, (0, gb), (w, gb), (0, 220, 220), 2)
            cv2.line(debug, (0, gc), (w, gc), (0, 0, 255), 2)
            print(f"[OK] Gap tìm thấy: y={gt} đến y={gb}, center={gc}, size={gb-gt}px")
            status = "CÁ PHÍA DƯỚI → SẼ CLICK" if fish_y > gc else "Cá phía trên → không click"
            print(f"     Cá y={fish_y}, Gap center={gc}: {status}")
        else:
            print("[!!] Không tìm thấy gap! Hãy chạy lúc cột đang hiển thị.")
    else:
        print("[!!] Không tìm thấy cá! Kiểm tra FISH_LOWER/UPPER hoặc tọa độ GAME_X/Y/W/H.")

    # Hiển thị fish mask
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    fish_mask = cv2.inRange(hsv, FISH_LOWER, FISH_UPPER)
    fish_mask[:int(h*0.15), :] = 0
    fish_mask[:int(h*0.20), w//2:] = 0
    fish_overlay = frame.copy()
    fish_overlay[fish_mask > 0] = [0, 255, 0]

    cv2.imshow("Result (ca=xanh la, gap=xanh lam/do)", debug)
    cv2.imshow("Fish Mask (xanh la = ca phat hien)", fish_overlay)

    print("\nNhấn phím bất kỳ để đóng...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    print("\n=== Hướng dẫn tinh chỉnh ===")
    print("- Cá không nhận: chỉnh FISH_LOWER/UPPER")
    print("- Gap sai: chỉnh CLICK_THRESHOLD")
    print("- Bot click quá ít: giảm CLICK_THRESHOLD (vd: 0.05)")
    print("- Bot click quá nhiều: tăng CLICK_THRESHOLD (vd: 0.20)")


# ─────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        calibrate()
    else:
        run_bot()
