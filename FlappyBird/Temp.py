import cv2
import numpy as np
import pygetwindow as gw
import ctypes
import mss
import time

ctypes.windll.shcore.SetProcessDpiAwareness(1)

GAME_REGION = {
    "left_offset": 540,
    "top_offset":  50,
    "width":       466,
    "height":      835,
}

win = gw.getWindowsWithTitle("Top Heroes")[0]

with mss.mss() as sct:
    print("⏳ Chuyển sang game đi, còn 5 giây...")
    time.sleep(3)
    
    region = {
        "left":   win.left + GAME_REGION["left_offset"],
        "top":    win.top  + GAME_REGION["top_offset"],
        "width":  GAME_REGION["width"],
        "height": GAME_REGION["height"],
    }
    shot  = sct.grab(region)
    frame = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
    hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Mask cột xám hiện tại
    mask_col = cv2.inRange(hsv, np.array([90, 10, 80]), np.array([140, 80, 180]))

    # Vẽ đường scan_x lên ảnh gốc để xem đang quét ở đâu
    scan_x = int(frame.shape[1] * 0.45)
    debug  = frame.copy()
    cv2.line(debug, (scan_x, 0), (scan_x, frame.shape[0]), (0, 255, 255), 2)

    # In ra giá trị HSV tại một số điểm trên cột
    # (để biết màu thực của cột là bao nhiêu)
    print("HSV tại các điểm giữa màn hình (x=233):")
    for y in range(50, 800, 50):
        h_val, s_val, v_val = hsv[y, 233]
        col_detected = "✅ CỘT" if mask_col[y, 233] > 0 else "❌"
        print(f"  y={y:4d}: H={h_val:3d} S={s_val:3d} V={v_val:3d}  {col_detected}")

    cv2.imwrite("debug_col_mask.png",  mask_col)
    cv2.imwrite("debug_scanline.png",  debug)
    cv2.imwrite("debug_original2.png", frame)
    print("\n✅ Đã lưu ảnh!")