import cv2
import numpy as np
import ArducamDepthCamera as ac
from ultralytics import YOLO
import pyttsx3

# MAX_DISTANCE value modifiable  is 2000 or 4000
MAX_DISTANCE=4000

engine = pyttsx3.init()

import subprocess

def say(text: str):
    subprocess.run(["espeak-ng",        
        "-s", "200",         # speed
        "-p", "40",          # pitch
        text])


class UserRect:
    def __init__(self) -> None:
        self.start_x = 0
        self.start_y = 0
        self.end_x = 0
        self.end_y = 0

    @property
    def rect(self):
        return (
            self.start_x,
            self.start_y,
            self.end_x - self.start_x,
            self.end_y - self.start_y,
        )

    @property
    def slice(self):
        return (slice(self.start_y, self.end_y), slice(self.start_x, self.end_x))

    @property
    def empty(self):
        return self.start_x == self.end_x and self.start_y == self.end_y


confidence_value = 30
selectRect, followRect = UserRect(), UserRect()


def getPreviewRGB(preview: np.ndarray, confidence: np.ndarray) -> np.ndarray:
    preview = np.nan_to_num(preview)
    preview[confidence < confidence_value] = (0, 0, 0)
    return preview


def on_mouse(event, x, y, flags, param):
    global selectRect, followRect

    if event == cv2.EVENT_LBUTTONDOWN:
        pass

    elif event == cv2.EVENT_LBUTTONUP:
        selectRect.start_x = x - 4
        selectRect.start_y = y - 4
        selectRect.end_x = x + 4
        selectRect.end_y = y + 4
    else:
        followRect.start_x = x - 4
        followRect.start_y = y - 4
        followRect.end_x = x + 4
        followRect.end_y = y + 4


def on_confidence_changed(value):
    global confidence_value
    confidence_value = value


def usage(argv0):
    print("Usage: python " + argv0 + " [options]")
    print("Available options are:")
    print(" -d        Choose the video to use")


def main():
    print("Arducam Depth Camera Demo.")
    print("  SDK version:", ac.__version__)

    cam = ac.ArducamCamera()
    cfg_path = None
    # cfg_path = "file.cfg"

    black_color = (0, 0, 0)
    white_color = (255, 255, 255)

    ret = 0
    if cfg_path is not None:
        ret = cam.openWithFile(cfg_path, 0)
    else:
        ret = cam.open(ac.Connection.CSI, 0)
    if ret != 0:
        print("Failed to open camera. Error code:", ret)
        return

    ret = cam.start(ac.FrameType.DEPTH)
    if ret != 0:
        print("Failed to start camera. Error code:", ret)
        cam.close()
        return

    cam.setControl(ac.Control.RANGE, MAX_DISTANCE)
    cam.setControl(ac.Control.EXPOSURE, 2000)

    r = cam.getControl(ac.Control.RANGE)

    info = cam.getCameraInfo()
    print(f"Camera resolution: {info.width}x{info.height}")

    # cv2.namedWindow("preview", cv2.WINDOW_AUTOSIZE)
    # cv2.setMouseCallback("preview", on_mouse)

    if info.device_type == ac.DeviceType.VGA:
        # Only VGA support confidence
        cv2.createTrackbar(
            "confidence", "preview", confidence_value, 255, on_confidence_changed
        )
    i = 0 
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    output_filename = 'depth_output.avi' # Use .mp4 if using mp4v codec
    out = cv2.VideoWriter('depth_output.avi', fourcc, 1,(240, 180))

    model = YOLO("best.pt")
    names = model.names 
    print("Starting preview... Press 'q' to quit.")
    try: 
        while True:
            frame = cam.requestFrame(2000)
            if frame is not None and isinstance(frame, ac.DepthData):
                depth_buf = frame.depth_data
                confidence_buf = frame.confidence_data

                # result_image = (depth_buf * (255.0 / r)).astype(np.uint8)
                # result_image = cv2.applyColorMap(result_image, cv2.COLORMAP_RAINBOW)
                # result_image = getPreviewRGB(result_image, confidence_buf)

                # cv2.normalize(confidence_buf, confidence_buf, 1, 0, cv2.NORM_MINMAX)
                # print("here")
                # results = model(result_image)

                CONF_THR = 30      # tune this
                MAX_MM   = r       # your range setting, e.g. 2000 or 4000

                # 1) Start from a copy so we don’t destroy original buffer
                depth = depth_buf.copy().astype(np.float32)
                conf  = confidence_buf.copy().astype(np.float32)

                # 2) Mask out low confidence pixels
                depth[conf < CONF_THR] = 0   # or np.nan

                # 3) Clip to a sane range
                depth = np.clip(depth, 0, MAX_MM)

                # 4) Normalize to 0..255 *after* masking + clipping
                depth_norm = (depth * (255.0 / MAX_MM)).astype(np.uint8)

                # 5) Reduce speckle: median blur works very well on ToF noise
                depth_norm = cv2.medianBlur(depth_norm, 5) s

                # 6) Apply colormap
                result_image = cv2.applyColorMap(depth_norm, cv2.COLORMAP_RAINBOW)

                # If you want to use confidence as an alpha mask instead of getPreviewRGB:
                mask = (conf >= CONF_THR).astype(np.uint8)
                mask = cv2.medianBlur(mask, 5)
                mask_3 = cv2.cvtColor(mask * 255, cv2.COLOR_GRAY2BGR)

                # Darken unreliable regions
                result_image = cv2.bitwise_and(result_image, mask_3)
                H, W = depth_buf.shape
                # Now run YOLO
                results = model(result_image, conf=0.30)
                annotated_frame = results[0].plot()
                res = results[0]
                CONF_THR = 30           # confidence threshold
                MARGIN_MM = 250        # cluster margin around nearest depth (tune this)

                H, W = depth_buf.shape

                for box in results[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                    # Clamp to valid pixel bounds
                    x1 = max(0, min(W - 1, x1))
                    x2 = max(0, min(W - 1, x2))
                    y1 = max(0, min(H - 1, y1))
                    y2 = max(0, min(H - 1, y2))

                    if x2 <= x1 or y2 <= y1:
                        continue

                    # Extract depth + confidence inside the box
                    roi_d = depth_buf[y1:y2, x1:x2].astype(np.float32)
                    roi_c = confidence_buf[y1:y2, x1:x2]

                    # Mask invalid or low-confidence values
                    mask = (roi_d > 0) & (roi_c >= CONF_THR)
                    valid = roi_d[mask]

                    if valid.size == 0:
                        dist_cm = None
                    else:
                        # Nearest depth cluster
                        d_min = float(np.percentile(valid, 5))      # mm

                        # Keep points within ±MARGIN_MM of object depth
                        near_mask = valid <= (d_min + MARGIN_MM)
                        obj_depths = valid[near_mask]

                        if obj_depths.size == 0:
                            dist_mm = d_min
                        else:
                            dist_mm = float(np.median(obj_depths))

                        # Convert mm → cm
                        dist_cm = dist_mm * 0.1
                    
                    
                    cls_id = int(box.cls[0])
                    print (cls_id)
                    conf_det = float(box.conf[0])
                    if (cls_id==0 and dist_cm < 250 and dist_cm >=130): 
                        print(f"Person distance: {dist_cm} cm")
                        say(f"Person ahead at {dist_cm:.0f} centimeters")
                        # engine.runAndWait()
                    elif (cls_id != 0 and dist_cm < 150 and dist_cm >=45): 
                        print(f"Obstacle distance: {dist_cm} cm")
                        # say(f"Obstacle detected ahead at distance {dist_cm:.0ff} centimeters")
                        engine.say(f"Obstacle detected ahead at distance {dist_cm:.0f} centimeters")
                        engine.runAndWait()

                    elif( dist_cm < 45):
                        print(" stop stop ")
                        # say("Stop, obstacle very close")
                        engine.say("Stop, obstacle very close")
                        engine.runAndWait()
                        # engine.runAndWait()
                    print(f"class {cls_id}, conf {conf_det:.2f}, distance {dist_cm} m")


                if results and len(results[0].boxes) > 0:
                    cv2.imwrite(f"detections.jpg", annotated_frame)

                # cv2.imshow("preview_confidence", confidence_buf)
                # cv2.imwrite(f"confidence){i}.png", confidence_buf)
                # print(confidence_buf)

                cv2.rectangle(result_image, followRect.rect, white_color, 1)
                if not selectRect.empty:
                    cv2.rectangle(result_image, selectRect.rect, black_color, 2)
                    print("select Rect distance:", np.mean(depth_buf[selectRect.slice]))

                # cv2.imshow("preview", result_image)
                # cv2.imwrite(f"depth_{i}.jpg", result_image)
                out.write(annotated_frame)
                i += 1
                cam.releaseFrame(frame)

            key = cv2.waitKey(1)
            if key == ord("q"):
                break

        cam.stop()
        cam.close()
        out.release()
    except KeyboardInterrupt:
        cam.stop()
        cam.close()
        out.release()
        print("Exiting...")


if __name__ == "__main__":
    main()
