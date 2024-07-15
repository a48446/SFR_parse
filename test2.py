import cv2
import time
import numpy as np

def test_stream_performance(rtsp_url, use_gpu=False):
    if use_gpu:
        print("Running stream test with GPU...")
        # 檢查是否有可用的 CUDA 裝置
        if cv2.cuda.getCudaEnabledDeviceCount() == 0:
            print("No CUDA device found. Switching to CPU.")
            use_gpu = False
        else:
            cv2.cuda.setDevice(0)
    else:
        print("Running stream test with CPU...")
    
    # 創建視頻捕捉對象
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print("Error: Could not open video stream.")
        return

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        if use_gpu:
            # 使用 GPU 處理
            gpu_frame = cv2.cuda_GpuMat()
            gpu_frame.upload(frame)
            # 假設我們對 GPU 幀執行一些操作
            processed_frame = cv2.cuda.cvtColor(gpu_frame, cv2.COLOR_BGR2GRAY)
            processed_frame.download()  # 如果需要顯示或進一步處理，則下載
        else:
            # 使用 CPU 處理
            processed_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 假設我們只處理100幀就結束
        if frame_count >= 100:
            break
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Processed {frame_count} frames in {elapsed_time:.2f} seconds on {'GPU' if use_gpu else 'CPU'}.")

    cap.release()

# 替換以下 URL 為你的實際 RTSP 流地址
rtsp_url = 'rtsp://192.168.0.30:554/stream1'

# 測試 CPU
test_stream_performance(rtsp_url, use_gpu=False)

# 測試 GPU (如果可用)
test_stream_performance(rtsp_url, use_gpu=True)
