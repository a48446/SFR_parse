#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ffmpeg
import numpy as np
import cv2

camera = 'rtsp://admin:Admin_12@192.168.137.2/stream1'

probe = ffmpeg.probe(camera)
video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
width = int(video_stream['width'])
height = int(video_stream['height'])

out = (
    ffmpeg
        .input(camera, rtsp_transport='tcp')
        .output('pipe:', format='rawvideo', pix_fmt='bgr24', loglevel="quiet", r=25)
        .run_async(pipe_stdout=True)
)
cnt_empty = 0
while True:
    in_bytes = out.stdout.read(height * width * 3)
    if not in_bytes:
        cnt_empty += 1
        if cnt_empty > 10:
            break
    cnt_empty = 0
    frame = np.frombuffer(in_bytes, dtype=np.uint8).reshape(height, width, 3)
    # to process frame
    cv2.imshow('test', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
