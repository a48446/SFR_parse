import ffmpeg
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageEnhance
from tkinter import filedialog
import threading
import queue
import datetime
from scipy import stats
from scipy.fftpack import fft
import time
import os

camera = 'rtsp://admin:Admin_12@192.168.137.2/stream1'
frame_queue = queue.Queue(maxsize=10)
roi_list = []
roi_ids = []
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
        frame = frame.resize((400, 300))  # Adjust this to match the canvas size
        imgtk = ImageTk.PhotoImage(image=frame)
        canvas.imgtk = imgtk
        canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
        
        # Redraw all ROIs
        for roi in roi_list:
            canvas.create_rectangle(*roi, outline='red', width=2)
            
    root.after(40, update_canvas)  # Adjust timing based on frame rate

def on_canvas_click(event):
    global current_roi
    if len(roi_list) < 5:
        current_roi = [event.x, event.y, event.x, event.y]
        roi_id = canvas.create_rectangle(*current_roi, outline='red', width=2, tags="current_roi")
        roi_ids.append(roi_id)

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
        update_roi_listbox()
        current_roi = None

def update_roi_listbox():
    roi_listbox.delete(0, tk.END)
    for roi in roi_list:
        roi_listbox.insert(tk.END, f"ROI: {roi}")

def clear_rois():
    global roi_list, roi_ids
    roi_list = []
    for roi_id in roi_ids:
        canvas.delete(roi_id)
    roi_ids = []
    update_roi_listbox()

def calculate_mtfs(label_idx):
    global current_frame
    if current_frame is not None:  # Ensure there is a frame available
        frame_image = Image.fromarray(current_frame)
        for idx, roi in enumerate(roi_list):
            sfr = SFR(frame_image, roi)
            results = sfr.calculate()
            mtf50 = results['MTF50']
            roi_mtf_labels[label_idx][idx].config(text=f'MTF={mtf50:.2f}')

def on_start():
    status_label.config(text="Connected")
    rtsp_url = f"rtsp://admin:Admin_12@192.168.137.2/stream1"
    start_rtsp_stream(rtsp_url)

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

root = tk.Tk()
root.title("MTF Test Interface")

# Organizing the layout using grid geometry manager
for i in range(12):  # Adjust the number of rows for your needs
    root.grid_rowconfigure(i, weight=1)
for i in range(6):  # Adjust the number of columns for your needs
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

clear_button = ttk.Button(root, text="Clear ROIs", command=clear_rois)
clear_button.grid(column=1, row=4, padx=5, pady=5, sticky='w')

angles = ['0', '45 - Face 1', '45 - Face 2', '45 - Face 3', '45 - Face 4']
roi_mtf_labels = []
for idx, angle in enumerate(angles):
    angle_label = ttk.Label(root, text=angle)
    angle_label.grid(column=0, row=idx+5, padx=5, pady=5, sticky='w')

    test_button = ttk.Button(root, text="Test", command=lambda idx=idx: calculate_mtfs(idx))
    test_button.grid(column=1, row=idx+5, padx=5, pady=5, sticky='w')

    mtf_labels = []
    for roi_idx in range(5):
        mtf_label = ttk.Label(root, text='MTF=')
        mtf_label.grid(column=2 + roi_idx, row=idx+5, padx=5, pady=5, sticky='w')
        mtf_labels.append(mtf_label)

    roi_mtf_labels.append(mtf_labels)

# Create a canvas for video streaming
canvas = tk.Canvas(root, width=400, height=300, bg='gray')
canvas.grid(column=0, row=10, rowspan=10, columnspan=6, padx=10, pady=10)
canvas.bind("<Button-1>", on_canvas_click)
canvas.bind("<B1-Motion>", on_canvas_drag)
canvas.bind("<ButtonRelease-1>", on_canvas_release)

# ROI listbox
roi_listbox_label = ttk.Label(root, text="Selected ROIs:")
roi_listbox_label.grid(column=0, row=20, padx=5, pady=5, sticky='w')

roi_listbox = tk.Listbox(root, height=5)
roi_listbox.grid(column=0, row=21, columnspan=6, padx=5, pady=5, sticky='w')

root.after(0, update_canvas)  # Start periodic updates
root.mainloop()
