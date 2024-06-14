import ffmpeg
import subprocess
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageEnhance
from tkinter import filedialog
import threading
import queue
import datetime
import re
from scipy import stats
from scipy.fftpack import fft
import time
import os

frame_queue = queue.Queue(maxsize=10)
roi_list = []
roi_ids = []
roi_labels = []
current_roi = None
current_frame = None

class SFR:
    def __init__(self, image, image_roi, gamma=0.5, oversampling_rate=4):
        self.image = image
        self.image_roi = self._validate_roi(image_roi)
        self.gamma = gamma
        self.oversampling_rate = oversampling_rate

    def _validate_roi(self, roi):
        x1, y1, x2, y2 = roi
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        return (x1, y1, x2, y2)

    def calculate(self):
        image = self.image.crop(self.image_roi).convert('L')
        image = image.transpose(Image.Transpose.ROTATE_90)
        pixels = np.array(image)
        esf, slope, intercept = self._get_esf_data(pixels, self.oversampling_rate)
        lsf = self._get_lsf_data(esf)
        sfr = self._get_sfr_data(lsf)
        mtf, mtf50, mtf50p = self._get_mtf_data(sfr, self.oversampling_rate)
        return {'MTF50': mtf50, 'MTF50P': mtf50p}

    def _get_esf_data(self, pixel_array, oversampling_rate):
        edge_idx_per_line = []
        for line in pixel_array:
            max_diff = 0
            last_px = line[0]
            max_idx = idx = 0
            for px in line:
                diff = abs(int(last_px) - int(px))
                if diff > max_diff:
                    max_diff = diff
                    max_idx = idx
                last_px = px
                idx += 1
            edge_idx_per_line.append(max_idx)
        slope, intercept, _, _, _ = stats.linregress(list(range(len(edge_idx_per_line))), edge_idx_per_line)
        inspection_width = 1
        while inspection_width <= len(pixel_array[0]):
            inspection_width *= 2
        inspection_width //= 2
        half_inspection_width = inspection_width / 2
        esf_sum = [0] * (inspection_width * oversampling_rate + 2)
        hit_count = [0] * (inspection_width * oversampling_rate + 2)
        x = y = 0
        for line in pixel_array:
            for px in line:
                if abs(x - (y * slope + intercept)) <= half_inspection_width + 1 / oversampling_rate:
                    idx = int((x - (y * slope + intercept) + half_inspection_width) * oversampling_rate + 1)
                    esf_sum[idx] += px
                    hit_count[idx] += 1
                x += 1
            y += 1
            x = 0
        hit_count = [1 if c == 0 else c for c in hit_count]
        return np.divide(esf_sum, hit_count).tolist(), slope, intercept

    def _get_lsf_data(self, esf_data):
        lsf_data = [0] * (len(esf_data) - 2)
        for idx in range(len(lsf_data)):
            lsf_data[idx] = (esf_data[idx + 2] - esf_data[idx]) / 2
        return lsf_data

    def _get_sfr_data(self, lsf_data):
        hamming_window = np.hamming(len(lsf_data)).tolist()
        windowed_lsf_data = np.multiply(lsf_data, hamming_window).tolist()
        raw_sfr_data = np.abs(fft(windowed_lsf_data)).tolist()
        sfr_base = raw_sfr_data[0]
        return [d / sfr_base for d in raw_sfr_data]

    def _get_mtf_data(self, sfr_data, oversampling_rate):
        mtf_data = [0] * int(len(sfr_data) / 2 / (oversampling_rate * 0.5))
        mtf50 = 0
        for idx in range(len(mtf_data)):
            freq = idx / (len(mtf_data) - 1)
            if freq == 0:
                mtf_data[idx] = sfr_data[idx]
            else:
                mtf_data[idx] = sfr_data[idx] * (np.pi * freq * 2 / oversampling_rate) / np.sin(np.pi * freq * 2 / oversampling_rate)
            if idx > 0 and mtf_data[idx] < 0.5 and mtf_data[idx - 1] >= 0.5:
                mtf50 = (idx - 1 + (0.5 - mtf_data[idx]) / (mtf_data[idx - 1] - mtf_data[idx])) / (len(mtf_data) - 1)
                break
        return mtf_data, mtf50, 0  # mtf50p not used in this example

def start_rtsp_stream(rtsp_url):
    def stream():
        global current_frame
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
            current_frame = frame  # Update the current frame

    thread = threading.Thread(target=stream)
    thread.daemon = True
    thread.start()

def update_canvas():
    if not frame_queue.empty():
        frame = frame_queue.get()
        frame = Image.fromarray(frame)
        frame = frame.resize((500, 400))  # Adjust this to match the canvas size
        imgtk = ImageTk.PhotoImage(image=frame)
        canvas.imgtk = imgtk
        canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
        draw_rois()  # Redraw the ROIs on the new frame
    root.after(40, update_canvas)  # Adjust timing based on frame rate

def on_canvas_click(event):
    global current_roi
    if len(roi_list) < 5:
        current_roi = [event.x, event.y, event.x, event.y]
        roi_id = canvas.create_rectangle(*current_roi, outline='red', width=2, tags="current_roi")
        roi_ids.append(roi_id)
        roi_label = canvas.create_text(event.x, event.y, anchor=tk.NW, text=f"ROI{len(roi_list)+1}", fill="red", font=("Arial", 10))
        roi_labels.append(roi_label)

def on_canvas_drag(event):
    global current_roi
    if current_roi:
        current_roi[2] = event.x
        current_roi[3] = event.y
        canvas.coords("current_roi", *current_roi)

def on_canvas_release(event):
    global current_roi
    if current_roi:
        roi_list.append(tuple(current_roi))
        canvas.delete("current_roi")
        roi_id = canvas.create_rectangle(*current_roi, outline='red', width=2)
        roi_ids.append(roi_id)
        roi_label = canvas.create_text(current_roi[0], current_roi[1], anchor=tk.NW, text=f"ROI{len(roi_list)}", fill="red", font=("Arial", 10))
        roi_labels.append(roi_label)
        update_roi_listbox()
        current_roi = None

def update_roi_listbox():
    roi_listbox.delete(0, tk.END)
    for i, roi in enumerate(roi_list):
        roi_listbox.insert(tk.END, f"ROI{i+1}: {roi}")

def clear_rois():
    global roi_list, roi_ids, roi_labels
    roi_list = []
    for roi_id in roi_ids:
        canvas.delete(roi_id)
    for roi_label in roi_labels:
        canvas.delete(roi_label)
    roi_ids = []
    roi_labels = []
    update_roi_listbox()

def draw_rois():
    for idx, roi in enumerate(roi_list):
        canvas.create_rectangle(*roi, outline='red', width=2)
        canvas.create_text(roi[0], roi[1], anchor=tk.NW, text=f"ROI{idx+1}", fill="red", font=("Arial", 10))

def calculate_mtfs(label_idx):
    global current_frame
    if current_frame is not None:  # Ensure there is a frame available
        frame_image = Image.fromarray(current_frame)
        for idx, roi in enumerate(roi_list):
            sfr = SFR(frame_image, roi)
            results = sfr.calculate()
            mtf50 = results['MTF50']
            roi_mtf_labels[label_idx][idx].config(text=f'MTF{idx+1}={mtf50:.2f}')

def on_start():
    ip = ip_entry.get()
    username = username_entry.get()
    password = password_entry.get()
    if not ip or not username or not password:
        status_label.config(text="Incomplete credentials", foreground="red")
        return
    
    rtsp_url = f"rtsp://{username}:{password}@{ip}/stream1"
    status_label.config(text="Connecting...", foreground="orange")

    try:
        # Validate credentials
        validate_command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/get?motorized_lens.info.ctrl_status']
        validate_result = subprocess.run(validate_command, capture_output=True, text=True, timeout=5)

        if validate_result.returncode != 0 or "Unauthorized" in validate_result.stdout:
            status_label.config(text="Invalid credentials", foreground="red")
            return

        status_label.config(text="Connected", foreground="green")
        start_rtsp_stream(rtsp_url)
    except subprocess.TimeoutExpired:
        status_label.config(text="Connection timed out", foreground="red")

def capture_screenshot():
    if canvas.imgtk:  # Ensure there is an image on the canvas
        now = datetime.datetime.now()
        formatted_time = now.strftime("%m%d_%H%M")
        default_filename = f"capturescreenshot_{formatted_time}.png"

        file_path = filedialog.asksaveasfilename(
            initialfile=default_filename,
            defaultextension='.png',
            filetypes=[("PNG files", "*.png")]
        )
        if file_path:
            canvas.imgtk._PhotoImage__photo.write(file_path, format='png')
            print("Screenshot saved at:", file_path)
        else:
            print("Screenshot not saved.")

def get_max_optical_zoom(ip, username, password):
    get_max = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/get?motorized_lens.info.max_optical_zoom']
    get_max_result = subprocess.run(get_max, capture_output=True, text=True)

    match = re.search(r'"motorized_lens\.info\.max_optical_zoom":\["ok","(\d+\.\d+)"\]', get_max_result.stdout)
    if match:
        max_optical_zoom = match.group(1)
        return max_optical_zoom
    else:
        print("Could not find max optical zoom value in the response.")
        return None

def monitor_status(ip, username, password):
    get_status = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/get?motorized_lens.info.ctrl_status']
    result = subprocess.run(get_status, capture_output=True, text=True)
    match = re.search(r'"motorized_lens\.info\.ctrl_status":\["ok","(\w+)"\]', result.stdout)
    if match:
        ctrl_status = match.group(1)
        return ctrl_status
    else:
        print("Could not find control status value in the response.")
        return None

def update_status():
    ip = ip_entry.get()
    username = username_entry.get()
    password = password_entry.get()
    if ip and username and password:
        status = monitor_status(ip, username, password)
        if status:
            camera_status_label.config(text=f"Camera status: {status}")
    root.after(1000, update_status)

def on_wide_end():
    ip = ip_entry.get()
    username = username_entry.get()
    password = password_entry.get()
    status = monitor_status(ip, username, password)
    if status == "idle":
        command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.zoom.move.absolute=1']
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            print(result.stdout)  # Print the output of the curl command
        except Exception as e:
            print(f"Error executing curl command: {e}")
    else:
        print("Camera is busy. Please wait until it is idle.")

def on_middle():
    ip = ip_entry.get()
    username = username_entry.get()
    password = password_entry.get()
    max_optical_zoom = get_max_optical_zoom(ip, username, password)
    min_optical_zoom = 1
    status = monitor_status(ip, username, password)
    if status == "idle":
        if max_optical_zoom:
            middle_optical_zoom = (float(max_optical_zoom) + min_optical_zoom) / 2
            command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.zoom.move.absolute={middle_optical_zoom}']
            try:
                result = subprocess.run(command, capture_output=True, text=True)
                print(result.stdout)
            except Exception as e:
                print(f"Error executing curl command: {e}")
    else:
        print("Camera is busy. Please wait until it is idle.")

def on_tele_end():
    ip = ip_entry.get()
    username = username_entry.get()
    password = password_entry.get()
    max_optical_zoom = get_max_optical_zoom(ip, username, password)
    command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.zoom.move.absolute={max_optical_zoom}']
    status = monitor_status(ip, username, password)
    if status == "idle":
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            print(result.stdout)
        except Exception as e:
            print(f"Error executing curl command: {e}")
    else:
        print("Camera is busy. Please wait until it is idle.")

def on_autofocus():
    ip = ip_entry.get()
    username = username_entry.get()
    password = password_entry.get()
    command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.focus.move.one_push=1']
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        print(result.stdout)  # Print the output of the curl command
    except Exception as e:
        print(f"Error executing curl command: {e}")

root = tk.Tk()
root.title("MTF Test Interface")

# Organizing the layout using grid geometry manager
for i in range(12):  # Adjust the number of rows for your needs
    root.grid_rowconfigure(i, weight=1)
for i in range(10):  # Adjust the number of columns for your needs
    root.grid_columnconfigure(i, weight=1)

# Define UI elements in the left grid
ip_label = ttk.Label(root, text="IP:")
ip_label.grid(column=0, row=0, sticky='w')
ip_entry = ttk.Entry(root)
ip_entry.grid(column=1, row=0, padx=5, pady=5, sticky='w')

start_button = ttk.Button(root, text="Start", command=on_start)
start_button.grid(column=0, row=1, padx=5, pady=5, sticky='w')

status_label = ttk.Label(root, text="Not Connected")
status_label.grid(column=1, row=1, padx=5, pady=5, sticky='w')

username_label = ttk.Label(root, text="Username")
username_label.grid(column=0, row=2, sticky='w')

username_entry = ttk.Entry(root)
username_entry.grid(column=1, row=2, sticky='w')

password_label = ttk.Label(root, text="Password")
password_label.grid(column=0, row=3, sticky='w')

password_entry = ttk.Entry(root, show="*")
password_entry.grid(column=1, row=3, sticky='w')

wide_end_button = ttk.Button(root, text="Wide end", command=on_wide_end)
wide_end_button.grid(column=0, row=4, padx=5, pady=5, sticky='w')

middle_button = ttk.Button(root, text="Middle", command=on_middle)
middle_button.grid(column=1, row=4, padx=5, pady=5, sticky='w')

tele_end_button = ttk.Button(root, text="Tele end", command=on_tele_end)
tele_end_button.grid(column=0, row=5, padx=5, pady=5, sticky='w')

autofocus_button = ttk.Button(root, text="Auto focus", command=on_autofocus)
autofocus_button.grid(column=1, row=5, padx=5, pady=5, sticky='w')

capture_button = ttk.Button(root, text="Capture Screenshot", command=capture_screenshot)
capture_button.grid(column=0, row=6, padx=5, pady=5, sticky='w')

camera_status_label = ttk.Label(root, text="Camera status: unknown")
camera_status_label.grid(column=1, row=6, padx=5, pady=5, sticky='w')

angles = ['0°', '45° - Face 1', '45° - Face 2', '45° - Face 3', '45° - Face 4']
roi_mtf_labels = []
for idx, angle in enumerate(angles):
    angle_label = ttk.Label(root, text=angle)
    angle_label.grid(column=0, row=7+idx, padx=5, pady=5, sticky='w')

    test_button = ttk.Button(root, text="Test", command=lambda idx=idx: calculate_mtfs(idx))
    test_button.grid(column=1, row=7+idx, padx=5, pady=5, sticky='w')

    mtf_labels = []
    for roi_idx in range(5):
        mtf_label = ttk.Label(root, text=f'MTF{roi_idx+1}=')
        mtf_label.grid(column=2 + roi_idx, row=7+idx, padx=5, pady=5, sticky='w')
        mtf_labels.append(mtf_label)

    roi_mtf_labels.append(mtf_labels)

# Create a canvas for video streaming
canvas = tk.Canvas(root, width=500, height=400, bg='gray')
canvas.grid(column=7, row=0, rowspan=20, columnspan=3, padx=10, pady=10)
canvas.bind("<Button-1>", on_canvas_click)
canvas.bind("<B1-Motion>", on_canvas_drag)
canvas.bind("<ButtonRelease-1>", on_canvas_release)

# ROI listbox
roi_listbox_label = ttk.Label(root, text="Selected ROIs:")
roi_listbox_label.grid(column=0, row=12, padx=5, pady=5, sticky='w')

roi_listbox = tk.Listbox(root, height=5)
roi_listbox.grid(column=1, row=12, padx=5, pady=5, sticky='w')

clear_button = ttk.Button(root, text="Clear ROIs", command=clear_rois)
clear_button.grid(column=1, row=13, padx=5, pady=5, sticky='w')

root.after(0, update_canvas)  # Start periodic updates
root.after(0, update_status)  # Start periodic status updates
root.mainloop()
