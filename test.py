import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk
import threading

def on_start():
    status_label.config(text="Connected")
    ip_address = no_entry.get()
    print(ip_address)
    rtsp_url = f"rtsp://{ip_address}"
    start_rtsp_stream(rtsp_url)

def start_rtsp_stream(rtsp_url):
    def stream():
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            messagebox.showerror("Error", "Unable to open video stream")
            return

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
            canvas.imgtk = imgtk

            canvas.update()

        cap.release()

    # Start the streaming in a separate thread
    thread = threading.Thread(target=stream)
    thread.daemon = True
    thread.start()

def capture_screenshot():
    print("Screenshot functionality to be added")

def get_mtf_value():
    # 在這裡添加您的 MTF 計算邏輯
    # 例如，調用某個 API 或者執行某種計算
    # 這裡我們簡單返回一個示例值
    return 0.85

def update_mtf_value(mtf_label):
    mtf_value = get_mtf_value()
    mtf_label.config(text=f'MTF={mtf_value:.2f}')
    print(f"Updated MTF Value: {mtf_value}")

root = tk.Tk()
root.title("MTF 測試界面")

# Start button and connection status
start_button = ttk.Button(root, text="Start", command=on_start)
start_button.grid(column=0, row=0, padx=5, pady=5)

status_label = ttk.Label(root, text="Not Connected")
status_label.grid(column=1, row=0, padx=5, pady=5)

# No. entry field
no_label = ttk.Label(root, text="No.")
no_label.grid(column=0, row=1, padx=5, pady=5)

no_entry = ttk.Entry(root)
no_entry.grid(column=1, row=1, padx=5, pady=5)

# Test angle label and capture screenshot button
test_angle_label = ttk.Label(root, text="Test angle")
test_angle_label.grid(column=0, row=2, padx=5, pady=5)

capture_button = ttk.Button(root, text="Capture Screenshot", command=capture_screenshot)
capture_button.grid(column=1, row=2, padx=5, pady=5)

# Test angle rows with Test buttons and MTF labels
angles = ['0', '45 - Face 1', '45 - Face 2', '45 - Face 3', '45 - Face 4']
mtf_labels = []
for idx, angle in enumerate(angles):
    angle_label = ttk.Label(root, text=angle)
    angle_label.grid(column=0, row=idx+3, padx=5, pady=5)

    mtf_label = ttk.Label(root, text='MTF=')
    mtf_label.grid(column=2, row=idx+3, padx=5, pady=5)
    mtf_labels.append(mtf_label)

    test_button = ttk.Button(root, text="Test", command=lambda label=mtf_label: update_mtf_value(label))
    test_button.grid(column=1, row=idx+3, padx=5, pady=5)

# 顯示區域的畫布（用於顯示視頻串流）
canvas = tk.Canvas(root, width=400, height=300, bg='gray')
canvas.grid(column=0, row=len(angles)+3, columnspan=3, padx=10, pady=10)

root.mainloop()
