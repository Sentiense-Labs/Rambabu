from picamera2 import Picamera2
import http.server
import socketserver
import cv2
import numpy as np
import signal
import sys

# ==========================
# LOAD OBJECT MODEL
# ==========================

CLASSES = [
    "background","aeroplane","bicycle","bird","boat",
    "bottle","bus","car","cat","chair","cow",
    "diningtable","dog","horse","motorbike","person",
    "pottedplant","sheep","sofa","train","tvmonitor"
]

net = cv2.dnn.readNetFromCaffe(
    "/home/rambabu/model/MobileNetSSD_deploy.prototxt",
    "/home/rambabu/model/MobileNetSSD_deploy.caffemodel"
)

print("Object detection model loaded")

# ==========================
# CAMERA
# ==========================

picam = Picamera2()
picam.configure(
    picam.create_video_configuration(
        main={"size": (640,480), "format": "RGB888"}
    )
)
picam.start()

# Safe shutdown
def shutdown_handler(sig, frame):
    print("\nStopping camera...")
    picam.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)

# ==========================
# HTML (NO SCROLL)
# ==========================

HTML = """<!DOCTYPE html>
<html>
<head>
<title>Object Detection</title>
<style>
html, body {
    margin:0;
    padding:0;
    height:100%;
    overflow:hidden;
    background:black;
}
img {
    width:100%;
    height:100%;
    object-fit:contain;
}
</style>
</head>
<body>
<img src="/stream.mjpg">
</body>
</html>
"""

# ==========================
# SERVER
# ==========================

class CamHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):

        if self.path == "/stream.mjpg":

            self.send_response(200)
            self.send_header("Content-type","multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            try:
                while True:
                    frame = picam.capture_array()

                    h, w = frame.shape[:2]

                    blob = cv2.dnn.blobFromImage(
                        cv2.resize(frame, (300,300)),
                        0.007843,
                        (300,300),
                        127.5
                    )

                    net.setInput(blob)
                    detections = net.forward()

                    for i in range(detections.shape[2]):
                        confidence = detections[0,0,i,2]

                        if confidence > 0.5:
                            idx = int(detections[0,0,i,1])
                            label = CLASSES[idx]

                            box = detections[0,0,i,3:7] * np.array([w,h,w,h])
                            x1,y1,x2,y2 = box.astype("int")

                            cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
                            cv2.putText(frame,label,(x1,y1-5),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.7,(0,255,0),2)

                    display = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    _, jpeg = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY,80])

                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(jpeg.tobytes())
                    self.wfile.write(b"\r\n")

            except:
                pass

        else:
            self.send_response(200)
            self.send_header("Content-type","text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())

PORT = 8000

class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

with ThreadingServer(("", PORT), CamHandler) as httpd:
    print("Object detection running at http://YOUR_PI_IP:8000")
    httpd.serve_forever()