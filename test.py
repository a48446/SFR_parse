import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading

class RTSPStream:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.cap = cv2.VideoCapture(rtsp_url)
        self.frame = None
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.update)
        self.thread.start()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join()
        self.cap.release()

class ROIApplication:
    def __init__(self, master, rtsp_url):
        self.master = master
        self.rtsp_stream = RTSPStream(rtsp_url)
        self.rtsp_stream.start()

        self.canvas = tk.Canvas(master, width=800, height=600, bg='gray')
        self.canvas.pack()

        self.roi_list = []
        self.current_roi = None

        self.bind_canvas_events()
        self.update_canvas()

    def bind_canvas_events(self):
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def on_canvas_click(self, event):
        self.current_roi = [event.x, event.y, event.x, event.y]

    def on_canvas_drag(self, event):
        if self.current_roi:
            self.current_roi[2] = event.x
            self.current_roi[3] = event.y
            self.canvas.delete("current_roi")
            self.canvas.create_rectangle(*self.current_roi, outline='red', width=2, tags="current_roi")

    def on_canvas_release(self, event):
        if self.current_roi:
            self.roi_list.append(tuple(self.current_roi))
            self.canvas.delete("current_roi")
            self.canvas.create_rectangle(*self.current_roi, outline='red', width=2)
            self.current_roi = None

    def update_canvas(self):
        frame = self.rtsp_stream.frame
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = Image.fromarray(frame)
            frame = frame.resize((800, 600))
            imgtk = ImageTk.PhotoImage(image=frame)
            self.canvas.imgtk = imgtk
            self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
        self.master.after(30, self.update_canvas)  # Adjust timing based on frame rate

def main():
    root = tk.Tk()
    root.geometry("800x600")

    rtsp_url = "rtsp://admin:1qaz!QAZ@192.168.0.30/stream1"  # Change this to your RTSP URL
    app = ROIApplication(root, rtsp_url)

    root.mainloop()
    app.rtsp_stream.stop()

if __name__ == "__main__":
    main()
