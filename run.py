#!/usr/bin/env python3
import os
import sys

# OpenCV'yi macOS'ta yalnızca AVFoundation ile sınırla; aksi halde OBSENSOR (Orbbec)
# eklentisi devreye girip anlamsız hatalar basıyor. cv2 yüklemeden ÖNCE ayarlanmalı.
if sys.platform == "darwin":
    os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_LIST", "AVFOUNDATION")

# Import the tkinter fix to patch the ScreenChanged error
import tkinter_fix

from modules import core

if __name__ == '__main__':
    core.run()
