import pyautogui
import time
import pygetwindow as gw
import ctypes
# Fix DPI Scaling để tọa độ không bị lệch
ctypes.windll.shcore.SetProcessDpiAwareness(1)

# --- CẤU HÌNH CHUỖI TỌA ĐỘ TẠI ĐÂY ---
# Định dạng: (x, y, delay_sau_khi_click)
ACTION_SEQUENCE = [
    (40, 720, 0.5),   
    (950, 930, 1.5), 
    # (820, 720, 0.5),
    (950, 720, 0.5),
    (950, 720, 0.5),
]

def run_sequence_bot():
    window_title = 'Top Heroes'
    
    try:
        # Tìm cửa sổ game
        win = gw.getWindowsWithTitle(window_title)[0]
        
        if win.isMinimized:
            win.restore()
        
        win.activate()
        time.sleep(1) 

        print(f"🚀 Bot đang chạy chuỗi {len(ACTION_SEQUENCE)} bước trên Desktop ảo.")
        print("💡 Nhấn Ctrl + C để dừng. Hãy chuyển sang Desktop khác để làm việc.")
        
        while True:        
            for _ in range(4):
                pyautogui.press('esc')
                for i, (rel_x, rel_y, delay) in enumerate(ACTION_SEQUENCE):
                    # Tính toán tọa độ tuyệt đối (luôn tính lại mỗi lần click phòng khi bạn di chuyển cửa sổ)
                    abs_x = win.left + rel_x
                    abs_y = win.top + rel_y

                    # Thực hiện di chuyển và click
                    # duration=0.1 giúp bot di chuyển chuột mượt mà, tránh bị hệ thống nghi ngờ
                    pyautogui.moveTo(abs_x, abs_y, duration=0.1)
                    pyautogui.click()
                
                    print(f"Bước {i+1}: Click ({rel_x}, {rel_y}) | Chờ {delay}s")
                    time.sleep(delay)
                pyautogui.press('esc')

            time.sleep(10)
            # break # Xoá dòng này nếu bạn muốn bot chạy mãi mãi

    except IndexError:
        print(f"❌ Không tìm thấy cửa sổ: {window_title}")
    except KeyboardInterrupt:
        print("\n🛑 Bot đã dừng bởi người dùng.")
    except Exception as e:
        print(f"❌ Lỗi: {e}")

if __name__ == "__main__":
    run_sequence_bot()