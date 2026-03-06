from picamera2 import Picamera2
import http.server
import socketserver
import face_recognition
import cv2
import os
import numpy as np

# ----------------------------
# Load Known Faces
# ----------------------------
known_encodings = []
known_names = []

for file in os.listdir("known_faces"):
    if file.lower().endswith((".jpg", ".jpeg", ".png")):
        image = face_recognition.load_image_file(f"known_faces/{file}")
        encodings = face_recognition.face_encodings(image)
        if len(encodings) > 0:
            known_encodings.append(encodings[0])
            known_names.append(os.path.splitext(file)[0])

print("Known faces loaded:", known_names)

# ----------------------------
# Start Camera
# ----------------------------
picam = Picamera2()
picam.configure(picam.create_video_configuration(main={"size": (640, 480)}))
picam.start()

# ----------------------------
# HTML Page
# ----------------------------
HTML = """<!DOCTYPE html>
<html>
<head>
<title>Face Recognition</title>
<style>
body { background:black; color:cyan; text-align:center; font-family:monospace; }
img { width:90%; margin-top:20px; }
</style>
</head>
<body>
<h2>Live Face Recognition</h2>
<img src="/stream.mjpg">
</body>
</html>
"""

# ----------------------------
# HTTP Handler
# ----------------------------
class CamHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):

        if self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            try:
                while True:
                    frame = picam.capture_array()
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    face_locations = face_recognition.face_locations(rgb)
                    face_encodings = face_recognition.face_encodings(rgb, face_locations)

                    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):

                        matches = face_recognition.compare_faces(known_encodings, face_encoding)
                        name = "Unknown"

                        face_distances = face_recognition.face_distance(known_encodings, face_encoding)

                        if len(face_distances) > 0:
                            best_match_index = np.argmin(face_distances)
                            if matches[best_match_index]:
                                name = known_names[best_match_index]

                        cv2.rectangle(frame, (left, top), (right, bottom), (0,255,0), 2)
                        cv2.putText(frame, name, (left, top - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)

                    _, jpeg = cv2.imencode(".jpg", frame)
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(jpeg.tobytes())
                    self.wfile.write(b"\r\n")

            except:
                pass

        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(HTML.encode())

# ----------------------------
# Start Server
# ----------------------------
PORT = 8000

class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

with ThreadingServer(("", PORT), CamHandler) as httpd:
    print(f"Face recognition running at http://<your-pi-ip>:{PORT}")
    httpd.serve_forever()