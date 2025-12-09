import logging
import math
import time

import cv2
import numpy as np
import keyboard

from grabbers import get_grabber
from controls.mouse import get_mouse_controls
from utils.fps import FPSCounter
from utils.nms import non_max_suppression
from utils.cv import merge_overlapping_boxes
from utils.timing import precise_sleep
from utils.win32 import get_window_rect
from config import CaptureRegion, adjust_region_to_multiple

from screen_to_world import pixels_to_counts_simple, pixels_to_counts_enhanced

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Config
WINDOW_TITLE = "aimlab_tb"
ACTIVATION_HOTKEY = 58  # CAPS-LOCK
AUTO_DEACTIVATE_AFTER = 60
SHOOT_ENABLED = True
SHOW_CV2 = True

GRABBER_TYPE = "mss"
OBS_DEVICE_INDEX = -1
OBS_DEVICE_NAME = "OBS Virtual Camera"

PAUSE_TIME = 0.09
SHOOT_INTERVAL = 0.05

# FOV settings
HORIZONTAL_FOV = 106.26
VERTICAL_FOV = 73.74
X360_COUNTS = 2727
COUNTS_PER_DEGREE = X360_COUNTS / 360.0

# Detection settings
HUE_POINT = 87
SPHERE_COLOR_RANGE = ((HUE_POINT, 100, 100), (HUE_POINT + 20, 255, 255))
MIN_TARGET_SIZE = (40, 40)
MAX_TARGET_SIZE = (150, 150)

# Runtime state
aim_active = False
activation_time = 0
correction = [0.0, 0.0]
last_movement = None


def get_capture_region() -> CaptureRegion:
    try:
        rect = get_window_rect(WINDOW_TITLE, (8, 30, 16, 39))
        region = CaptureRegion(
            left=rect[0],
            top=rect[1],
            width=rect[2],
            height=rect[3],
        )
    except Exception as e:
        logger.warning(f"Could not find window '{WINDOW_TITLE}': {e}")
        region = CaptureRegion(left=0, top=0, width=1920, height=1080)

    return adjust_region_to_multiple(region, 32)


def init_grabber(grabber_type: str):
    if grabber_type == "obs_vc":
        return get_grabber(
            grabber_type,
            device_index=OBS_DEVICE_INDEX,
            device_name=OBS_DEVICE_NAME,
        )
    return get_grabber(grabber_type)


def check_center_dot(img, crop_size: int = 5, threshold: float = 0.25) -> bool:
    if img is None or img.size == 0:
        return False

    h, w = img.shape[:2]
    center_x = w // 2
    center_y = h // 2

    x1 = max(0, min(center_x - crop_size // 2, w - crop_size))
    y1 = max(0, min(center_y - crop_size // 2, h - crop_size))
    x2 = x1 + crop_size
    y2 = y1 + crop_size

    dot_region = img[y1:y2, x1:x2]
    if dot_region.shape[0] == 0 or dot_region.shape[1] == 0:
        return False

    hsv = cv2.cvtColor(dot_region, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array(SPHERE_COLOR_RANGE[0], dtype=np.uint8),
        np.array(SPHERE_COLOR_RANGE[1], dtype=np.uint8),
    )

    return np.count_nonzero(mask) > (mask.size * threshold)


def detect_targets(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array(SPHERE_COLOR_RANGE[0], dtype=np.uint8),
        np.array(SPHERE_COLOR_RANGE[1], dtype=np.uint8),
    )

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rectangles = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if (MIN_TARGET_SIZE[0] <= w <= MAX_TARGET_SIZE[0] and
                MIN_TARGET_SIZE[1] <= h <= MAX_TARGET_SIZE[1]):
            rectangles.append((x, y, w, h))

    return rectangles


def select_best_target(rectangles, screen_center, exclude_threshold=73):
    if not rectangles:
        return None

    candidates = []
    for rect in rectangles:
        x, y, w, h = rect
        mid_x = x + w // 2
        mid_y = y + h // 2
        dist = math.dist(screen_center, (mid_x, mid_y))

        if dist > exclude_threshold:
            candidates.append((rect, dist))

    if not candidates:
        candidates = [
            (rect, math.dist(screen_center, (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)))
            for rect in rectangles
        ]

    cluster_threshold = 200
    clusters = []
    used = set()

    for i, (rect_i, dist_i) in enumerate(candidates):
        if i in used:
            continue

        cluster = [(rect_i, dist_i)]
        used.add(i)
        mid_i = (rect_i[0] + rect_i[2] // 2, rect_i[1] + rect_i[3] // 2)

        for j, (rect_j, dist_j) in enumerate(candidates):
            if j in used:
                continue

            mid_j = (rect_j[0] + rect_j[2] // 2, rect_j[1] + rect_j[3] // 2)
            if math.dist(mid_i, mid_j) < cluster_threshold:
                cluster.append((rect_j, dist_j))
                used.add(j)

        if len(cluster) > 1:
            clusters.append(cluster)

    if clusters:
        best_cluster = min(clusters, key=lambda cl: min(r[1] for r in cl))
        return min(best_cluster, key=lambda r: r[1])[0]

    return min(candidates, key=lambda r: r[1])[0]


def main_loop():
    global aim_active, activation_time, correction, last_movement

    region = get_capture_region()
    grabber = init_grabber(GRABBER_TYPE)
    mouse = get_mouse_controls("win32")
    fps = FPSCounter()
    font = cv2.FONT_HERSHEY_SIMPLEX

    screen_center = (region.width // 2, region.height // 2)
    grab_area = region.to_dict()

    last_shoot_time = None

    logger.info(f"Starting capture: {region.width}x{region.height}")
    logger.info(f"Press CAPS-LOCK to toggle aiming")

    while True:
        img = grabber.get_image(grab_area)
        if img is None:
            continue

        # Shooting logic
        if SHOOT_ENABLED and aim_active:
            can_shoot = (last_shoot_time is None or
                         time.perf_counter() > last_shoot_time + SHOOT_INTERVAL)

            if can_shoot and check_center_dot(img):
                mouse.press("left")
                precise_sleep(0.001)
                mouse.release("left")
                last_shoot_time = time.perf_counter()

        # Target detection
        rectangles = detect_targets(img)
        if not rectangles:
            if SHOW_CV2:
                current_fps = fps()
                cv2.putText(img, f"{current_fps:.1f} | targets = 0", (20, 120),
                            font, 1.7, (0, 255, 0), 7, cv2.LINE_AA)
                cv2.imshow("AimBot", cv2.resize(img, (1280, 720)))
                cv2.waitKey(1)
            continue

        targets_count = len(rectangles)

        # Apply NMS
        if len(rectangles) > 1:
            boxes = np.array([(x, y, x + w, y + h) for x, y, w, h in rectangles])
            nms_boxes = non_max_suppression(boxes, overlap_thresh=0.3)
            rectangles = [(b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in nms_boxes]

        # Merge overlapping
        rectangles = merge_overlapping_boxes(rectangles)

        # Select best target
        target = select_best_target(rectangles, screen_center)
        if target is None:
            continue

        x, y, w, h = target
        mid_x = x + w // 2
        mid_y = y + h // 2

        # Draw debug info
        if SHOW_CV2:
            for rect in rectangles:
                rx, ry, rw, rh = rect
                cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), (255, 0, 0), 2)

            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.circle(img, (mid_x, mid_y), 10, (0, 0, 255), -1)

        # Aim movement
        if aim_active:
            dx, dy = pixels_to_counts_enhanced(
                target_xy=(mid_x, mid_y),
                win_wh=(region.width, region.height),
                fov_deg_pair=(HORIZONTAL_FOV, VERTICAL_FOV),
                counts_per_deg_x=COUNTS_PER_DEGREE,
            )

            # Distance-based boost
            x_diff = abs(mid_x - screen_center[0])
            y_diff = abs(mid_y - screen_center[1])

            if x_diff > screen_center[0] / 4:
                dx = int(dx * 1.05)
            if x_diff > screen_center[0] / 3:
                dx = int(dx * 1.05)

            if y_diff > screen_center[1] / 4:
                dy = int(dy * 1.05)
            if y_diff > screen_center[1] / 2:
                dy = int(dy * 1.05)

            last_movement = (dx, dy)
            mouse.move_relative(dx, dy)
            precise_sleep(PAUSE_TIME)

        # Display
        if SHOW_CV2:
            current_fps = fps()
            status = "AIM ON" if aim_active else "AIM OFF"
            cv2.putText(img, f"{current_fps:.1f} | {status} | targets = {targets_count}",
                        (20, 120), font, 1.5, (0, 255, 0), 5, cv2.LINE_AA)
            cv2.imshow("AimBot", cv2.resize(img, (1280, 720)))
            cv2.waitKey(1)


def toggle_aim(*args):
    global aim_active, activation_time
    aim_active = not aim_active
    if aim_active:
        activation_time = time.perf_counter()
        logger.info("Aim ACTIVATED")
    else:
        logger.info("Aim DEACTIVATED")


def perform_180(*args):
    mouse = get_mouse_controls("win32")
    turn_counts = int(COUNTS_PER_DEGREE * 180 + correction[0])
    mouse.move_relative(-turn_counts, 0)
    logger.info(f"180 turn: {-turn_counts} counts")


def return_crosshair(*args):
    global last_movement
    if last_movement is not None:
        mouse = get_mouse_controls("win32")
        mouse.move_relative(-last_movement[0], -last_movement[1])
        last_movement = None
        logger.info("Crosshair returned")


def adjust_correction_x(*args):
    global correction
    correction[0] += 0.1
    logger.info(f"X correction: {correction[0]:.1f}")


def adjust_correction_y(*args):
    global correction
    correction[1] += 0.1
    logger.info(f"Y correction: {correction[1]:.1f}")


keyboard.add_hotkey(ACTIVATION_HOTKEY, toggle_aim)
keyboard.add_hotkey("shift+q", perform_180)
keyboard.add_hotkey("shift+b", return_crosshair)
keyboard.add_hotkey("shift+x", adjust_correction_x)
keyboard.add_hotkey("shift+y", adjust_correction_y)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        cv2.destroyAllWindows()
