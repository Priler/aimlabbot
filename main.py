import logging, os, math, sys

from utils.grabbers.mss import Grabber as MSSGrabber
from utils.grabbers.obs_vc import Grabber
from pygrabber.dshow_graph import FilterGraph
from utils.fps import FPS
import cv2
import multiprocessing
from queue import Empty
import numpy as np
from utils.nms import non_max_suppression_fast
from utils.cv2 import filter_rectangles

from utils.controls.mouse.win32 import MouseControls
from utils.win32 import WinHelper
from utils.cv2 import resize_image_to_fit_multiply_of_32
import keyboard

import time
from utils.time import sleep
# from screen_to_world import get_move_angle__new as get_move_angle
# from ___screen_to_world import pixels_to_counts_single_shot
from screen_to_world import pixels_to_counts_simple, pixels_to_counts_enhanced

#config
ACTIVATION_HOTKEY = 58  # 58 = CAPS-LOCK
AUTO_DEACTIVATE_AFTER = 60  # seconds or None (default Aim Lab map time is 60 seconds)
_shoot = True
_show_cv2 = True

obs_vc_device_index = -1 # -1 to find by the given name
obs_vc_device_name = "OBS Virtual Camera"

# the bigger these values, the more accurate and fail-safe bot will behave
_pause = 0.09
_shoot_interval = 0.05  # seconds

# used by the script
game_window_rect = WinHelper.GetWindowRect("aimlab_tb", (8, 30, 16, 39))  # cut the borders
game_window_rect = resize_image_to_fit_multiply_of_32(list(game_window_rect))
_ret = None
_aim = False
_activation_time = 0
_correction = [0, 0]
_attempts = 0
_ret_center = [0, 0]
_target_shoot = False

def init_grabber():
    grabber = MSSGrabber()

    if grabber.type == "obs_vc":
        if obs_vc_device_index != -1:
            # init device by given index
            grabber.obs_vc_init(obs_vc_device_index)
        else:
            # init device by given name
            graph = FilterGraph()

            try:
                device = grabber.obs_vc_init(graph.get_input_devices().index(obs_vc_device_name))
            except ValueError as e:
                logging.error(f'Could not find OBS VC device with name "{obs_vc_device_name}"')
                logging.error(e)
                os._exit(1)
    
    return grabber



def check_dot(img, debug=False):
    """
    Check if the center of the image contains a blue dot (hue around 87)
    
    Args:
        img: Image from cv2.VideoCapture (BGR format)
        debug: If True, prints debug information
    
    Returns:
        bool: True if blue dot is detected
    """
    if img is None or img.size == 0:
        if debug:
            print("Invalid or empty image")
        return False
    
    h, w = img.shape[:2]
    if debug:
        print(f"Image dimensions: {w}x{h}")
    
    # Define crop size (6x6 pixel area)
    crop_size = 5

    # Calculate center dot coordinates with offset
    # center_x = int(w / 2 + 5)  # Using w instead of img.shape[1] for clarity
    # center_y = int(h / 2 + 28)  # Using h instead of img.shape[0] for clarity
    center_x = int((w / 2))  # Using w instead of img.shape[1] for clarity
    center_y = int((h / 2))  # Using h instead of img.shape[0] for clarity
    
    if debug:
        print(f"Target center: ({center_x}, {center_y})")

    # Ensure the crop area is within image bounds
    x1 = max(0, min(center_x - crop_size//2, w - crop_size))
    y1 = max(0, min(center_y - crop_size//2, h - crop_size))
    x2 = x1 + crop_size
    y2 = y1 + crop_size
    
    if debug:
        print(f"Crop area: ({x1}, {y1}) to ({x2}, {y2})")
    
    # Crop the region of interest
    dot_img = img[y1:y2, x1:x2]
    
    if dot_img.shape[0] == 0 or dot_img.shape[1] == 0:
        if debug:
            print("Cropped area is empty")
        return False

    # Convert cropped region to HSV
    dot_img_hsv = cv2.cvtColor(dot_img, cv2.COLOR_BGR2HSV)
    hue_point = 87
    # Make the range wider and lower the saturation/value thresholds for more sensitivity
    sphere_color = ((hue_point, 100, 100), (hue_point + 20, 255, 255))  # HSV
    mask = cv2.inRange(dot_img_hsv, np.array(sphere_color[0], dtype=np.uint8),
                            np.array(sphere_color[1], dtype=np.uint8))

    # Lower the required percentage for detection to increase sensitivity
    print(np.count_nonzero(mask), " > ", (mask.size * 0.25))
    return np.count_nonzero(mask) > (mask.size * 0.25)


def cv2_process():
    global _aim, _shoot, _ret, _target_shoot, _pause, _shoot_interval, _show_cv2, game_window_rect, _activation_time, _correction, _attempts

    fps = FPS()
    font = cv2.FONT_HERSHEY_SIMPLEX
    _last_shoot = None
    # grabber = init_grabber()
    grabber = init_grabber()

    mouse = MouseControls()
    # print(mouse.get_position())


    fov = [106.26, 73.74]  # horizontal, vertical
    HFOV, VFOV = fov

    # x360 = 16364  # x value to rotate on 360 degrees
    x360 = 2727  # x value to rotate on 360 degrees
    counts_per_degree = x360 / 360.0

    x360_x = 2727
    x1_x = x360_x / 360.0

    x1 = x360/360
    x_full_hor = x1 * fov[0]

    center_dot = {"x": int(game_window_rect[0] + (game_window_rect[2]/2)),
                                     "y": int(
                                         game_window_rect[1] + (game_window_rect[3]/2))}

    # 2420 = 53.13 grads
    # 360 grads = 16,400 # 16364

    while True:
        img = grabber.get_image({"left": int(game_window_rect[0]), "top": int(game_window_rect[1]), "width": int(game_window_rect[2]), "height": int(game_window_rect[3])})
        if img is None:
            break

        # if _ret is not None:
        #     # return the mouse to base position and proceed again
        #     mouse.move_relative(int(_ret[0]), int(_ret[1]))
        #     _ret = None
        #     # sleep(_pause)
        #     continue

        # Try shoot if currently aiming at the target
        _target_shoot = False
        if _last_shoot is None or time.perf_counter() > (_last_shoot + _shoot_interval) and _shoot:
            _attempts += 1

            # detect if aiming the target (more accurate)
            if check_dot(img):
                _attempts = 0
                _target_shoot = True

                # click
                mouse.hold_mouse()
                sleep(0.001)
                mouse.release_mouse()
                sleep(0.001)

                _last_shoot = time.perf_counter()
                # done_sem.release()
                # continue
            else:
                _target_shoot = False


        # Mask and infere blue spheres
        # OpenCV HSV Scale (H: 0-179, S: 0-255, V: 0-255)
        hue_point = 87
        sphere_color = ((hue_point, 100, 100), (hue_point + 20, 255, 255))  # HSV
        min_target_size = (40, 40)
        max_target_size = (150, 150)

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(sphere_color[0], dtype=np.uint8),
                            np.array(sphere_color[1], dtype=np.uint8))

        contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rectangles = []

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if (w >= min_target_size[0] and h >= min_target_size[1])\
                    and (w <= max_target_size[0] and h <= max_target_size[1]):
                rectangles.append((int(x), int(y), int(w), int(h)))

        if not rectangles:
            continue

        if _show_cv2:
            for rect in rectangles:
                x, y, w, h = rect
                cv2.rectangle(img, (x, y), (x + w, y + h), [255, 0, 0], 6)
                img = cv2.putText(img, f"{(x + w, y + h)}", (x, y-10), font,
                                    .5, (0, 255, 0), 1, cv2.LINE_AA)


        # max targets count is 1, everything else is considered FP
        rectangles = rectangles
        targets_count = len(rectangles)

        # Apply NMS
        rectangles = np.array(non_max_suppression_fast(np.array(rectangles), overlapThresh=0.3))

        # Filter rectangles (join intersections)
        rectangles = filter_rectangles(rectangles.tolist())
        # Exclude rectangles that are near the center of the screen (the ones we're currently aiming at)
        center = [960, 540]
        distance_threshold = 100  # You can adjust this value
        exclude_threshold = 73    # Exclude targets within this distance from center

        filtered_rects = []
        for rect in rectangles:
            x, y, w, h = rect
            mid_x = int((x + (x + w)) / 2)
            mid_y = int((y + (y + h)) / 2)
            dist = math.dist(center, [mid_x, mid_y])
            if dist > exclude_threshold:
                filtered_rects.append((rect, dist))

        if not filtered_rects:
            # If all targets are too close to center, fallback to original rectangles
            filtered_rects = [(rect, math.dist(center, [int((rect[0] + (rect[0] + rect[2])) / 2), int((rect[1] + (rect[1] + rect[3])) / 2)])) for rect in rectangles]

        # prioritize multiple closest targets that are close to each other over a single closest
        # Find clusters of targets that are close to each other
        cluster_threshold = distance_threshold  # distance between targets to be considered a cluster
        clusters = []
        used = set()
        for i, (rect_i, dist_i) in enumerate(filtered_rects):
            cluster = [filtered_rects[i]]
            used.add(i)
            mid_i = [int((rect_i[0] + (rect_i[0] + rect_i[2])) / 2), int((rect_i[1] + (rect_i[1] + rect_i[3])) / 2)]
            for j, (rect_j, dist_j) in enumerate(filtered_rects):
                if i == j or j in used:
                    continue
                mid_j = [int((rect_j[0] + (rect_j[0] + rect_j[2])) / 2), int((rect_j[1] + (rect_j[1] + rect_j[3])) / 2)]
                if math.dist(mid_i, mid_j) < cluster_threshold:
                    cluster.append(filtered_rects[j])
                    used.add(j)
            if len(cluster) > 1:
                clusters.append(cluster)

        if clusters:
            # If there are clusters, pick the cluster closest to center, then the closest target in that cluster
            cluster = min(clusters, key=lambda cl: min(r[1] for r in cl))
            aim_rect = min(cluster, key=lambda r: r[1])[0]
        else:
            # Fallback to single closest target
            aim_rect = min(filtered_rects, key=lambda r: r[1])[0]


        # show bounding boxes
        rectangles = [aim_rect]
        for rect in rectangles:
            x, y, w, h = rect
            if _show_cv2:
                cv2.rectangle(img, (x, y), (x + w, y + h), [0, 255, 0], 2)


        # AIM (if set)
        if _aim:
            # prepare coords
            mid_x = int((x+(x+w))/2)
            mid_y = int((y+(y+h))/2)
            #if _show_cv2:
            #    cv2.circle(img, (mid_x, mid_y), 10, (0, 0, 255), -1)

            dx, dy = pixels_to_counts_enhanced(
                target_xy=(mid_x, mid_y),
                win_wh=(game_window_rect[2], game_window_rect[3]), 
                fov_deg_pair=(HFOV, VFOV),
                counts_per_deg_x=x1_x
            )

            xdiff = abs(mid_x - center_dot["x"])
            ydiff = abs(mid_y - center_dot["y"])

            if xdiff > (center_dot["x"]/4):
                dx = int(dx * 1.05)
            if xdiff > (center_dot["x"]/3):
                dx = int(dx * 1.05)

            if ydiff > (center_dot["y"]/4):
                dy = int(dy * 1.05)
            if ydiff > (center_dot["y"]/2):
                dy = int(dy * 1.05)

            # if dx > 200:
            #     dx = 200

            # if dy > 100:
            #     dy = 100

            rel_diff = [dx, dy]

            _ret = rel_diff

            print(_target_shoot)
            mouse.move_relative(rel_diff[0], rel_diff[1])
            sleep(_pause)

            # click
            # sleep(0.001)
            # mouse.hold_mouse()
            # sleep(0.001)
            # mouse.release_mouse()
            # sleep(0.001)

            # sleep(_pause)
            # _aim = False

        # # Auto deactivate aiming and/or shooting after N seconds
        # if AUTO_DEACTIVATE_AFTER is not None:
        #     if _activation_time+AUTO_DEACTIVATE_AFTER < time.perf_counter():
        #         _aim = False

        # cv stuff
        # img = mask
        if not 'targets_count' in locals():
            targets_count = 0
        if _show_cv2:
            img = cv2.putText(img, f"{fps():.2f} | targets = {targets_count}", (20, 120), font,
                                1.7, (0, 255, 0), 7, cv2.LINE_AA)
            img = cv2.resize(img, (1280, 720))
            # cv2.imshow("test", cv2.cvtColor(img, cv2.COLOR_RGB2BGRA))
            # mask = cv2.resize(mask, (1280, 720))
            cv2.imshow("test", img)
            cv2.waitKey(1)


def switch_shoot_state(triggered, hotkey):
    global _aim, _activation_time
    _aim = not _aim  # inverse value

    if not _aim:
        _ret = None
    else:
        _activation_time = time.perf_counter()


keyboard.add_hotkey(ACTIVATION_HOTKEY, switch_shoot_state, args=('triggered', 'hotkey'))

def perform_180(triggered, hotkey):
    global _ret
    # x360 = 16364  # x value to rotate on 360 degrees
    x360 = 2727  # x value to rotate on 360 degrees
    x1 = x360/360 # 180

    print(f"PERFORMING 180: x by {-int(x360 + _correction[0])} with correction set to {_correction[0]}")

    mouse = MouseControls()
    mouse.move_relative(-int((x1 * 180) + _correction[0]), 0)

keyboard.add_hotkey("shift+q", perform_180, args=('triggered', 'hotkey'))

def return_crosshair(triggered, hotkey):
    global _ret
    x360 = 2727  # x value to rotate on 360 degrees
    x1 = x360/360

    if _ret is not None:
        mouse = MouseControls()
        # return the mouse to base position and proceed again
        mouse.move_relative(-int(x1 * _ret[0]), -int(x1 * _ret[1]))
        _ret = None
        # sleep(_pause)

keyboard.add_hotkey("shift+b", return_crosshair, args=('triggered', 'hotkey'))


def x_correct_angles(triggered, hotkey):
    global _correction

    _correction[0] += 0.1

    print("CORRECTION X", _correction)
keyboard.add_hotkey("shift+x", x_correct_angles, args=('triggered', 'hotkey'))


def y_correct_angles(triggered, hotkey):
    global _correction

    _correction[1] += 0.1

    print("CORRECTION Y", _correction)
keyboard.add_hotkey("shift+y", y_correct_angles, args=('triggered', 'hotkey'))


if __name__ == "__main__":
    cv2_process()
