import pyautogui
import time

print("Di chuột đến GÓC TRÁI TRÊN của vùng mini game...")
time.sleep(5)
x1, y1 = pyautogui.position()
print(f"Góc trái trên: x={x1}, y={y1}")

print("Di chuột đến GÓC PHẢI DƯỚI của vùng mini game...")
time.sleep(5)
x2, y2 = pyautogui.position()
print(f"Góc phải dưới: x={x2}, y={y2}")

print(f"\nKết quả:")
print(f"GAME_X, GAME_Y, GAME_W, GAME_H = {x1}, {y1}, {x2-x1}, {y2-y1}")