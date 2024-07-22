import os
import re
import cv2
import sys
import time
import threading
import datetime
import subprocess
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from scipy import stats
from scipy.fftpack import fft
from tkinter import ttk, filedialog
from multiprocessing import Queue, set_start_method, freeze_support
import xml.etree.ElementTree as ET
import pandas as pd
import json

class MTFApplication:
    def __init__(self, master):
        self.master = master
        self.roi_list = []
        self.current_roi = None
        self.device_var = tk.StringVar(value="SPD-T5390")
        self.rtsp_url = None
        self.current_frame = None
        self.stream_resolution = None
        self.test_counters = [0] * 5
        self.mtf_threshold_center = 0.5
        self.mtf_threshold_surround = 0.5
        self.mtf_delta_threshold = 0.1
        self.mtf_results = [[] for _ in range(5)]
        self.engineer_mode = False
        self.config_file = 'config.json'
        self.threshold_profiles = {
            "Profile 1": {"mtf_threshold_center": 0.5, "mtf_threshold_surround": 0.5, "mtf_delta_threshold": 0.1},
            "Profile 2": {"mtf_threshold_center": 0.6, "mtf_threshold_surround": 0.6, "mtf_delta_threshold": 0.15},
            "Profile 3": {"mtf_threshold_center": 0.7, "mtf_threshold_surround": 0.7, "mtf_delta_threshold": 0.2}
        }
        self.current_profile = tk.StringVar(value="Profile 1")
        self.load_thresholds()
        self.setup_ui()
        self.apply_threshold_profile(self.current_profile.get())
        self.disable_controls()

        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_thresholds(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.threshold_profiles.update(config)
        else:
            self.save_thresholds()

    def save_thresholds(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.threshold_profiles, f)

    def setup_ui(self):
        self.create_widgets()
        self.arrange_grid()
        self.bind_canvas_events()

    def create_widgets(self):
        self.ip_label = ttk.Label(self.master, text="IP:")
        self.ip_entry = ttk.Entry(self.master)
        self.device_label = ttk.Label(self.master, text="Device:")
        self.device_combobox = ttk.Combobox(self.master, textvariable=self.device_var)
        self.device_combobox['values'] = ("SPD-T5390", "SPD-T5391", "SPD-T5373", "SPD-T5375", "other")
        self.username_label = ttk.Label(self.master, text="Username:")
        self.username_entry = ttk.Entry(self.master)
        self.password_label = ttk.Label(self.master, text="Password:")
        self.password_entry = ttk.Entry(self.master, show="*")
        self.engineer_password_label = ttk.Label(self.master, text="Engineer Password:")
        self.engineer_password_entry = ttk.Entry(self.master, show="*")
        self.profile_label = ttk.Label(self.master, text="Threshold Profile:")
        self.profile_combobox = ttk.Combobox(self.master, textvariable=self.current_profile)
        self.profile_combobox['values'] = list(self.threshold_profiles.keys())
        self.profile_combobox.bind("<<ComboboxSelected>>", self.on_profile_change)
        self.start_button = ttk.Button(self.master, text="Start", command=self.on_start)
        self.engineer_mode_button = ttk.Button(self.master, text="Enter Engineer Mode", command=self.toggle_engineer_mode)
        self.engineer_mode_label = ttk.Label(self.master, text="OFF", foreground="red")
        self.status_label = ttk.Label(self.master, text="Not Connected")
        self.roi_listbox_label = ttk.Label(self.master, text="Selected ROIs:")
        self.roi_listbox = tk.Listbox(self.master, height=5)
        self.clear_button = ttk.Button(self.master, text="Clear ROIs", command=self.clear_rois)
        self.threshold_label_center = ttk.Label(self.master, text="Center Threshold:")
        self.threshold_entry_center = ttk.Entry(self.master)
        self.threshold_entry_center.insert(0, str(self.mtf_threshold_center))
        self.threshold_entry_center.config(state='disabled')
        self.threshold_label_surround = ttk.Label(self.master, text="Corner Threshold:")
        self.threshold_entry_surround = ttk.Entry(self.master)
        self.threshold_entry_surround.insert(0, str(self.mtf_threshold_surround))
        self.threshold_entry_surround.config(state='disabled')
        self.threshold_label_delta = ttk.Label(self.master, text="Corner Diff Threshold:")
        self.threshold_entry_delta = ttk.Entry(self.master)
        self.threshold_entry_delta.insert(0, str(self.mtf_delta_threshold))
        self.threshold_entry_delta.config(state='disabled')
        self.capture_button = ttk.Button(self.master, text="Capture Screenshot", command=self.capture_screenshot)
        self.export_button = ttk.Button(self.master, text="Export Excel", command=self.export_to_excel)
        self.wide_end_button = ttk.Button(self.master, text="Wide end", command=self.on_wide_end)
        self.middle_button = ttk.Button(self.master, text="Middle", command=self.on_middle)
        self.tele_end_button = ttk.Button(self.master, text="Tele end", command=self.on_tele_end)
        self.autofocus_button = ttk.Button(self.master, text="Auto focus", command=self.on_autofocus)
        self.camera_status_label = ttk.Label(self.master, text="Camera status: unknown")
        angles = ['0°', '45° - Face 1', '45° - Face 2', '45° - Face 3', '45° - Face 4']
        self.roi_mtf_labels = []
        self.roi_diff_labels = []
        self.roi_status_labels = []
        self.test_counter_labels = []
        roi_labels = ["MTF_UL", "MTF_UR", "MTF_LL", "MTF_LR", "MTF_C"]
        for idx, angle in enumerate(angles):
            angle_label = ttk.Label(self.master, text=angle)
            angle_label.grid(column=0, row=13 + idx, padx=5, pady=5, sticky='w')
            test_button = ttk.Button(self.master, text="Test", command=lambda idx=idx: self.calculate_mtfs(idx))
            test_button.grid(column=1, row=13 + idx, padx=5, pady=5, sticky='w')
            test_counter_label = ttk.Label(self.master, text=f"Count: {self.test_counters[idx]}")
            test_counter_label.grid(column=2, row=13 + idx, padx=5, pady=5, sticky='w')
            self.test_counter_labels.append(test_counter_label)
            mtf_labels = []
            diff_label = ttk.Label(self.master, text="Diff=")
            status_label = ttk.Label(self.master, text="Status:")
            for roi_idx in range(5):
                mtf_label = ttk.Label(self.master, text=f'{roi_labels[roi_idx]}=')
                mtf_label.grid(column=3 + roi_idx * 2, row=13 + idx, padx=5, pady=5, sticky='e')
                mtf_labels.append(mtf_label)
            diff_label.grid(column=13, row=13 + idx, padx=5, pady=5, sticky='w')
            status_label.grid(column=14, row=13 + idx, padx=5, pady=5, sticky='w')
            self.roi_mtf_labels.append(mtf_labels)
            self.roi_diff_labels.append(diff_label)
            self.roi_status_labels.append(status_label)

    def arrange_grid(self):
        self.device_label.grid(row=0, column=0, sticky='w')
        self.device_combobox.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        self.ip_label.grid(row=1, column=0, sticky='w')
        self.ip_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        self.username_label.grid(row=2, column=0, sticky='w')
        self.username_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        self.password_label.grid(row=3, column=0, sticky='w')
        self.password_entry.grid(row=3, column=1, padx=5, pady=5, sticky='w')
        self.engineer_password_label.grid(row=3, column=2, sticky='w')
        self.engineer_password_entry.grid(row=3, column=3, padx=5, pady=5, sticky='w')
        self.profile_label.grid(row=5, column=2, sticky='w')
        self.profile_combobox.grid(row=5, column=3, padx=5, pady=5, sticky='w')
        self.start_button.grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.status_label.grid(row=4, column=1, padx=5, pady=5, sticky='w')
        self.engineer_mode_button.grid(row=4, column=2, padx=5, pady=5, sticky='w')
        self.engineer_mode_label.grid(row=4, column=3, padx=5, pady=5, sticky='w')
        self.wide_end_button.grid(row=5, column=0, padx=5, pady=5, sticky='w')
        self.middle_button.grid(row=5, column=1, padx=5, pady=5, sticky='w')
        self.tele_end_button.grid(row=6, column=0, padx=5, pady=5, sticky='w')
        self.autofocus_button.grid(row=6, column=1, padx=5, pady=5, sticky='w')
        self.capture_button.grid(row=6,column=2, columnspan=2, padx=5, pady=5, sticky='w')
        self.roi_listbox_label.grid(row=8, column=0, sticky='w')
        self.roi_listbox.grid(row=8, column=1, padx=5, pady=5, sticky='w')
        self.clear_button.grid(row=9, column=0, sticky='w')
        self.threshold_label_center.grid(row=7, column=2, padx=5, pady=5, sticky='w')
        self.threshold_entry_center.grid(row=7, column=3, padx=5, pady=5, sticky='w')
        self.threshold_label_surround.grid(row=8, column=2, padx=5, pady=5, sticky='w')
        self.threshold_entry_surround.grid(row=8, column=3, padx=5, pady=5, sticky='w')
        self.threshold_label_delta.grid(row=9, column=2, padx=5, pady=5, sticky='w')
        self.threshold_entry_delta.grid(row=9, column=3, padx=5, pady=5, sticky='w')
        self.export_button.grid(row=19, column=13, padx=5, pady=5, sticky='w')
        self.camera_status_label.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky='w')
        self.roi_listbox.bind("<Double-1>", self.edit_roi)

    def bind_canvas_events(self):
        pass

    def on_profile_change(self, event):
        profile_name = self.current_profile.get()
        self.apply_threshold_profile(profile_name)

    def apply_threshold_profile(self, profile_name):
        profile = self.threshold_profiles.get(profile_name, {})
        self.mtf_threshold_center = profile.get('mtf_threshold_center', 0.5)
        self.mtf_threshold_surround = profile.get('mtf_threshold_surround', 0.5)
        self.mtf_delta_threshold = profile.get('mtf_delta_threshold', 0.1)
        self.threshold_entry_center.delete(0, tk.END)
        self.threshold_entry_center.insert(0, str(self.mtf_threshold_center))
        self.threshold_entry_surround.delete(0, tk.END)
        self.threshold_entry_surround.insert(0, str(self.mtf_threshold_surround))
        self.threshold_entry_delta.delete(0, tk.END)
        self.threshold_entry_delta.insert(0, str(self.mtf_delta_threshold))
        self.save_thresholds()

    def on_start(self):
        ip = self.ip_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        if not ip or not username or not password:
            self.status_label.config(text="Incomplete credentials", foreground="red")
            return
        self.rtsp_url = f"rtsp://{username}:{password}@{ip}/stream1"
        self.status_label.config(text="Connecting...", foreground="orange")
        try:
            validate_command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/get?motorized_lens.info.ctrl_status']
            validate_result = subprocess.run(validate_command, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            if validate_result.returncode != 0 or "Unauthorized" in validate_result.stdout:
                self.status_label.config(text="Invalid credentials", foreground="red")
                return
            self.status_label.config(text="Connected", foreground="green")
            self.start_opencv_stream(self.rtsp_url)
            self.enable_controls()
            self.monitor_camera_status(ip, username, password)
        except subprocess.TimeoutExpired:
            self.status_label.config(text="Connection timed out", foreground="red")

    def start_opencv_stream(self, rtsp_url):
        self.stream_thread = threading.Thread(target=self.display_opencv_stream, args=(rtsp_url,))
        self.stream_thread.daemon = True
        self.stream_thread.start()

    def display_opencv_stream(self, rtsp_url):
        ip = self.ip_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        curl_command = [
            'curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}',
            f'http://{ip}/cgi-bin/get?encode.profile.1.config'
        ]
        result = subprocess.run(curl_command, capture_output=True, text=True)
        match = re.search(r'(\d+x\d+)/', result.stdout)
        if match:
            max_resolution_str = match.group(1)
            max_resolution = tuple(map(int, max_resolution_str.split('x')))
            self.stream_resolution = max_resolution
        else:
            return

        window_width, window_height = (1920, 1080)
        cap = cv2.VideoCapture(rtsp_url)
        cv2.namedWindow("RTSP Stream", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("RTSP Stream", window_width, window_height)
        cv2.setMouseCallback("RTSP Stream", self.on_opencv_mouse_event)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            self.current_frame = frame

            display_frame = cv2.resize(frame, (window_width, window_height))
            for idx, (roi, label) in enumerate(self.roi_list):
                scale_x = window_width / self.stream_resolution[0]
                scale_y = window_height / self.stream_resolution[1]
                scaled_roi = (
                    int(roi[0] * scale_x), int(roi[1] * scale_y),
                    int(roi[2] * scale_x), int(roi[3] * scale_y)
                )
                cv2.rectangle(display_frame, (scaled_roi[0], scaled_roi[1]), (scaled_roi[2], scaled_roi[3]), (0, 0, 255), 2)
                cv2.putText(display_frame, label, (scaled_roi[0], scaled_roi[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

            cv2.imshow("RTSP Stream", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

        self.stream_thread = threading.Thread(target=self.display_opencv_stream, args=(rtsp_url,))
        self.stream_thread.daemon = True
        self.stream_thread.start()

    def display_opencv_stream_fixed_resolution(self, rtsp_url):
        fixed_width, fixed_height = self.stream_resolution
        cap = cv2.VideoCapture(rtsp_url)
        cv2.namedWindow("RTSP Stream", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("RTSP Stream", fixed_width, fixed_height)
        cv2.setMouseCallback("RTSP Stream", self.on_opencv_mouse_event)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            self.current_frame = frame

            display_frame = frame.copy()
            for idx, (roi, label) in enumerate(self.roi_list):
                cv2.rectangle(display_frame, (roi[0], roi[1]), (roi[2], roi[3]), (0, 0, 255), 2)
                cv2.putText(display_frame, label, (roi[0], roi[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

            display_frame = cv2.resize(display_frame, (1920, 1080))
            cv2.imshow("RTSP Stream", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

    def on_opencv_mouse_event(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.roi_list) < 5:
                scale_x = self.stream_resolution[0] / 1920
                scale_y = self.stream_resolution[1] / 1080
                self.current_roi = [int(x * scale_x), int(y * scale_y), int(x * scale_x), int(y * scale_y)]
        elif event == cv2.EVENT_MOUSEMOVE and self.current_roi is not None:
            scale_x = self.stream_resolution[0] / 1920
            scale_y = self.stream_resolution[1] / 1080
            self.current_roi[2] = int(x * scale_x)
            self.current_roi[3] = int(y * scale_y)
        elif event == cv2.EVENT_LBUTTONUP:
            if self.current_roi is not None:
                roi_positions = ["UL", "UR", "LL", "LR", "C"]
                roi_label = f"ROI_{roi_positions[len(self.roi_list)]}"
                self.roi_list.append((tuple(self.current_roi), roi_label))
                self.update_roi_listbox()
                self.current_roi = None

    def update_roi_listbox(self):
        self.roi_listbox.delete(0, tk.END)
        for i, (roi, label) in enumerate(self.roi_list):
            self.roi_listbox.insert(tk.END, f"{label}: {roi}")

    def clear_rois(self):
        self.roi_list = []
        self.update_roi_listbox()

    def edit_roi(self, event):
        selected_index = self.roi_listbox.curselection()
        if not selected_index:
            return
        selected_index = selected_index[0]
        roi, label = self.roi_list[selected_index]

        edit_window = tk.Toplevel(self.master)
        edit_window.title(f"Edit {label}")

        labels = ['X1:', 'Y1:', 'X2:', 'Y2:']
        entries = []
        for i, val in enumerate(roi):
            label_widget = ttk.Label(edit_window, text=labels[i])
            label_widget.grid(row=i, column=0, padx=5, pady=5)
            entry = ttk.Entry(edit_window)
            entry.insert(0, val)
            entry.grid(row=i, column=1, padx=5, pady=5)
            entries.append(entry)

        def on_save():
            new_roi = tuple(int(entry.get()) for entry in entries)
            self.roi_list[selected_index] = (new_roi, label)
            self.update_roi_listbox()
            edit_window.destroy()

        save_button = ttk.Button(edit_window, text="Save", command=on_save)
        save_button.grid(row=4, column=0, columnspan=2, pady=5)

    def capture_screenshot(self):
        if self.current_frame is not None:
            now = datetime.datetime.now()
            formatted_time = now.strftime("%Y%m%d%H%M")
            default_filename = f"capturescreenshot_{formatted_time}.png"
            file_path = filedialog.asksaveasfilename(initialfile=default_filename, defaultextension='.png', filetypes=[("PNG files", "*.png")])
            if file_path:
                frame_rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                image.save(file_path, format='png')
                print("Screenshot saved at:", file_path)
            else:
                print("Screenshot not saved.")

    def get_max_optical_zoom(self, ip, username, password):
        get_max = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/get?motorized_lens.info.max_optical_zoom']
        get_max_result = subprocess.run(get_max, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        match = re.search(r'"motorized_lens\.info\.max_optical_zoom":\["ok","(\d+\.\d+)"\]', get_max_result.stdout)
        if match:
            max_optical_zoom = match.group(1)
            return max_optical_zoom
        else:
            return None

    def monitor_camera_status(self, ip, username, password):
        def update_status():
            while True:
                status = self.monitor_status(ip, username, password)
                if status:
                    self.camera_status_label.config(text=f"Camera status: {status}")
                time.sleep(5)
        threading.Thread(target=update_status, daemon=True).start()

    def monitor_status(self, ip, username, password):
        get_status = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/get?motorized_lens.info.ctrl_status']
        result = subprocess.run(get_status, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        match = re.search(r'"motorized_lens\.info\.ctrl_status":\["ok","(\w+)"\]', result.stdout)
        if match:
            ctrl_status = match.group(1)
            return ctrl_status
        else:
            return None

    def on_wide_end(self):
        self.clear_rois()
        ip = self.ip_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        status = self.monitor_status(ip, username, password)
        device_type = self.device_var.get()
        if device_type[0:3] == "SPD":
            command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?ptz.zoom.move.absolute=100']
            if status == "idle" or status == "done":
                try:
                    result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    pass
            else:
                pass
        else:
            if status == "idle" or status == "done":
                command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.zoom.move.absolute=1']
                try:
                    result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    pass
            else:
                pass

    def on_middle(self):
        self.clear_rois()
        ip = self.ip_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        max_optical_zoom = self.get_max_optical_zoom(ip, username, password)
        min_optical_zoom = 1
        status = self.monitor_status(ip, username, password)
        device_type = self.device_var.get()

        if device_type[0:3] == "SPD":
            device_list = device_type.split("-")[0:4][1]
            if device_list == "T5390":
                max_optical_zoom = 3000
            if device_list == "T5391":
                max_optical_zoom = 2200
            if device_list == "T5373":
                max_optical_zoom = 3000
            if device_list == "T5375":
                max_optical_zoom = 4200

            if status == "idle" or status == "done":
                middle_optical_zoom = (
                    float(max_optical_zoom) + min_optical_zoom) / 2
                command = [
                    'curl',
                    '--cookie',
                    'ipcamera=test',
                    '--digest',
                    '-u',
                    f'{username}:{password}',
                    f'http://{ip}/cgi-bin/set?ptz.zoom.move.absolute={middle_optical_zoom}']
                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    pass
            else:
                pass
        if status == "idle" or status == "done":
            if max_optical_zoom:
                middle_optical_zoom = (
                    float(max_optical_zoom) + min_optical_zoom) / 2
                command = [
                    'curl',
                    '--cookie',
                    'ipcamera=test',
                    '--digest',
                    '-u',
                    f'{username}:{password}',
                    f'http://{ip}/cgi-bin/set?motorized_lens.zoom.move.absolute={middle_optical_zoom}']
                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    pass
        else:
            pass

    def on_tele_end(self):
        self.clear_rois()
        ip = self.ip_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        status = self.monitor_status(ip, username, password)
        device_type = self.device_var.get()
        if device_type[0:3] == "SPD":
            if status == "idle" or status == "done":
                if device_type == "SPD-T5390":
                    zoom_value = 3000
                elif device_type == "SPD-T5391":
                    zoom_value = 2200
                elif device_type == "SPD-T5373":
                    zoom_value = 3000
                elif device_type == "SPD-T5375":
                    zoom_value = 4200
                command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?ptz.zoom.move.absolute={zoom_value}']
                try:
                    result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    pass
            else:
                pass
        else:
            max_optical_zoom = self.get_max_optical_zoom(ip, username, password)
            if status == "idle" or status == "done":
                command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.zoom.move.absolute={max_optical_zoom}']
                try:
                    result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    pass
            else:
                pass

    def on_autofocus(self):
        ip = self.ip_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        device_type = self.device_var.get()
        if device_type[0:3] == "SPD":
            first_command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?ptz.focus.mode=manual']
            result = subprocess.run(first_command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?ptz.focus.manual.move.one_push=1']
        else:
            command = ['curl', '--cookie', 'ipcamera=test', '--digest', '-u', f'{username}:{password}', f'http://{ip}/cgi-bin/set?motorized_lens.focus.move.one_push=1']
        try:
            result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            pass

    def calculate_mtfs(self, label_idx):
        self.mtf_threshold_center = float(self.threshold_entry_center.get())
        self.mtf_threshold_surround = float(self.threshold_entry_surround.get())
        self.mtf_delta_threshold = float(self.threshold_entry_delta.get())

        if self.current_frame is not None:
            self.test_counters[label_idx] += 1
            self.test_counter_labels[label_idx].config(text=f"Count: {self.test_counters[label_idx]}")
            frame_image = Image.fromarray(self.current_frame)
            mtf_values = []
            min_mtf = float('inf')
            max_mtf = 0
            for idx, (roi, label) in enumerate(self.roi_list):
                sfr = SFR(frame_image, roi)
                results = sfr.calculate()
                mtf50 = results['MTF50']
                mtf_values.append(mtf50)
                roi_labels = ["MTF_UL", "MTF_UR", "MTF_LL", "MTF_LR", "MTF_C"]
                color = "red" if mtf50 < self.mtf_threshold_surround and label != "ROI_C" else "black"
                color = "red" if label == "ROI_C" and mtf50 < self.mtf_threshold_center else color
                self.roi_mtf_labels[label_idx][idx].config(text=f'{roi_labels[idx]}={mtf50:.2f}', foreground=color)
            self.mtf_results[label_idx] = mtf_values
            corner_diff = max(mtf_values[:-1]) - min(mtf_values[:-1])
            delta_pass = corner_diff <= self.mtf_delta_threshold
            overall_status = "Pass" if all(m >= self.mtf_threshold_surround for m in mtf_values[:-1]) and mtf_values[-1] >= self.mtf_threshold_center and delta_pass else "Fail"
            color = "red" if not delta_pass else "black"
            self.roi_diff_labels[label_idx].config(text=f'Diff={corner_diff:.2f}', foreground=color)
            self.roi_status_labels[label_idx].config(text=overall_status, foreground=("green" if overall_status == "Pass" else "red"))
        self.save_thresholds()

    def enable_controls(self):
        self.wide_end_button.config(state=tk.NORMAL)
        self.middle_button.config(state=tk.NORMAL)
        self.tele_end_button.config(state=tk.NORMAL)
        self.autofocus_button.config(state=tk.NORMAL)
        self.capture_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        for idx, angle in enumerate(self.roi_mtf_labels):
            for label in angle:
                label.config(state=tk.NORMAL)

    def disable_controls(self):
        self.wide_end_button.config(state=tk.DISABLED)
        self.middle_button.config(state=tk.DISABLED)
        self.tele_end_button.config(state=tk.DISABLED)
        self.autofocus_button.config(state=tk.DISABLED)
        self.capture_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        for idx, angle in enumerate(self.roi_mtf_labels):
            for label in angle:
                label.config(state=tk.DISABLED)

    def toggle_engineer_mode(self):
        engineer_password = self.engineer_password_entry.get()
        if engineer_password == "TopView@30":
            if not self.engineer_mode:
                self.engineer_mode = True
                self.engineer_mode_button.config(text="Engineer Mode: ON")
                self.engineer_mode_label.config(text="ON", foreground="green")
                self.threshold_entry_center.config(state='normal')
                self.threshold_entry_surround.config(state='normal')
                self.threshold_entry_delta.config(state='normal')
            else:
                self.engineer_mode = False
                self.engineer_mode_button.config(text="Engineer Mode: OFF")
                self.engineer_mode_label.config(text="OFF", foreground="red")
                self.threshold_entry_center.config(state='disabled')
                self.threshold_entry_surround.config(state='disabled')
                self.threshold_entry_delta.config(state='disabled')
            self.save_thresholds()
        else:
            pass

    def export_to_excel(self):
        now = datetime.datetime.now()
        formatted_time = now.strftime("%Y%m%d%H%M")
        data = {
            'Angle': ['0°', '45° - Face 1', '45° - Face 2', '45° - Face 3', '45° - Face 4'],
            'Count': self.test_counters,
            'Result': [],
            'Corner_diff': [],
            'Center_TH': [self.mtf_threshold_center] * 5,
            'Corner_TH': [self.mtf_threshold_surround] * 5,
            'Corner_diff_TH': [self.mtf_delta_threshold] * 5,
        }
        mtf_labels = ['MTF_UL', 'MTF_UR', 'MTF_LL', 'MTF_LR', 'MTF_C']
        
        for label in mtf_labels:
            data[label] = []

        for i in range(5):
            if i < len(self.mtf_results) and len(self.mtf_results[i]) == 5:
                mtf_values = self.mtf_results[i]
                min_mtf = min(mtf_values[:-1])
                max_mtf = max(mtf_values[:-1])
                corner_diff = max_mtf - min_mtf
                data['Corner_diff'].append(corner_diff)
                center_pass = mtf_values[-1] >= self.mtf_threshold_center
                surround_pass = all(m >= self.mtf_threshold_surround for m in mtf_values[:-1])
                delta_pass = corner_diff <= self.mtf_delta_threshold
                result = "Pass" if center_pass and surround_pass and delta_pass else "Fail"
                data['Result'].append(result)
            else:
                mtf_values = [None] * 5
                data['Corner_diff'].append(None)
                data['Result'].append("Fail")
            
            for j, label in enumerate(mtf_labels):
                data[label].append(mtf_values[j])

        df = pd.DataFrame(data)
        file_path = filedialog.asksaveasfilename(initialfile=f"MTFTestResults_{formatted_time}", defaultextension='.xlsx', filetypes=[("Excel files", "*.xlsx")])
        if file_path:
            df.to_excel(file_path, index=False)

    def on_closing(self):
        self.mtf_threshold_center = float(self.threshold_entry_center.get())
        self.mtf_threshold_surround = float(self.threshold_entry_surround.get())
        self.mtf_delta_threshold = float(self.threshold_entry_delta.get())
        self.save_thresholds()
        self.master.destroy()

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
        if self.image is None:
            return {'MTF50': 0, 'MTF50P': 0}
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
        return mtf_data, mtf50, 0

def main():
    set_start_method("spawn")
    root = tk.Tk()
    root.title("MTFTestInterface-v2.3")
    root.geometry("1100x600")
    app = MTFApplication(root)
    root.mainloop()

if __name__ == "__main__":
    freeze_support()
    main()
