import pyautogui, time
time.sleep(3)  # Di chuột vào góc trên-trái mini-game
print(pyautogui.position())  # → ghi lại (x, y)
# Di chuột vào góc dưới-phải
print(pyautogui.position())  # → tính width/height