import ffmpeg
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import queue

camera = 'rtsp://admin:Admin_12@192.168.137.2/stream1'
frame_queue = queue.Queue(maxsize=10)

def start_rtsp_stream(rtsp_url):
    def stream():
        probe = ffmpeg.probe(rtsp_url)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        width = int(video_stream['width'])
        height = int(video_stream['height'])

        out = (
            ffmpeg
                .input(rtsp_url, rtsp_transport='tcp')
                .output('pipe:', format='rawvideo', pix_fmt='bgr24', loglevel="quiet", r=25)
                .run_async(pipe_stdout=True)
        )

        while True:
            in_bytes = out.stdout.read(width * height * 3)
            if not in_bytes:
                break
            frame = np.frombuffer(in_bytes, dtype=np.uint8).reshape(height, width, 3)
            if not frame_queue.full():
                frame_queue.put(frame)

    thread = threading.Thread(target=stream)
    thread.daemon = True
    thread.start()

def update_canvas():
    if not frame_queue.empty():
        frame = frame_queue.get()
        frame = Image.fromarray(frame)
        frame = frame.resize((400, 300))  # Adjust this to match the canvas size
        imgtk = ImageTk.PhotoImage(image=frame)
        canvas.imgtk = imgtk
        canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
    root.after(40, update_canvas)  # Adjust timing based on frame rate

def on_canvas_click(event):
    if canvas.imgtk:  # Check if the image is present
        new_window = tk.Toplevel(root)
        new_window.title("Full-size Image")
        img_label = tk.Label(new_window, image=canvas.imgtk)
        img_label.pack()

def on_start():
    status_label.config(text="Connected")
    rtsp_url = f"rtsp://admin:Admin_12@192.168.137.2/stream1"
    start_rtsp_stream(rtsp_url)

def capture_screenshot():
    print("Screenshot functionality to be added")

def get_mtf_value():
    return 0.85

def update_mtf_value(mtf_label):
    mtf_value = get_mtf_value()
    mtf_label.config(text=f'MTF={mtf_value:.2f}')
    print(f"Updated MTF Value: {mtf_value}")

root = tk.Tk()
root.title("MTF 測試界面")

# Organizing the layout using grid geometry manager
for i in range(6):  # Adjust the number of rows for your needs
    root.grid_rowconfigure(i, weight=1)
for i in range(4):  # Adjust the number of columns for your needs
    root.grid_columnconfigure(i, weight=1)

# Define UI elements in the left grid
start_button = ttk.Button(root, text="Start", command=on_start)
start_button.grid(column=0, row=0, padx=5, pady=5, sticky='w')

status_label = ttk.Label(root, text="Not Connected")
status_label.grid(column=1, row=0, padx=5, pady=5, sticky='w')

username_label = ttk.Label(root, text="Username")
username_label.grid(column=0, row=1, sticky='w')

username_entry = ttk.Entry(root)
username_entry.grid(column=1, row=1, sticky='w')

password_label = ttk.Label(root, text="Password")
password_label.grid(column=0, row=2, sticky='w')

password_entry = ttk.Entry(root, show="*")
password_entry.grid(column=1, row=2, sticky='w')

capture_button = ttk.Button(root, text="Capture Screenshot", command=capture_screenshot)
capture_button.grid(column=1, row=3, padx=5, pady=5, sticky='w')

angles = ['0', '45 - Face 1', '45 - Face 2', '45 - Face 3', '45 - Face 4']
mtf_labels = []
for idx, angle in enumerate(angles):
    angle_label = ttk.Label(root, text=angle)
    angle_label.grid(column=0, row=idx+4, padx=5, pady=5, sticky='w')

    mtf_label = ttk.Label(root, text='MTF=')
    mtf_label.grid(column=2, row=idx+4, padx=5, pady=5, sticky='w')
    mtf_labels.append(mtf_label)

    test_button = ttk.Button(root, text="Test", command=lambda label=mtf_label: update_mtf_value(label))
    test_button.grid(column=1, row=idx+4, padx=5, pady=5, sticky='w')

# Create a canvas for video streaming
canvas = tk.Canvas(root, width=400, height=300, bg='gray')
canvas.grid(column=3, row=0, rowspan=10, padx=10, pady=10)
canvas.bind("<Button-1>", on_canvas_click)

root.after(0, update_canvas)  # Start periodic updates
root.mainloop()
