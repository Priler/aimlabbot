import logging, os, math, sys

from utils.grabbers.mss import Grabber as MSSGrabber
from utils.grabbers.obs_vc import Grabber
from pygrabber.dshow_graph import FilterGraph
from utils.fps import FPS
import cv2
import multiprocessing
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
from ___screen_to_world import get_move_angle__new3

#config
ACTIVATION_HOTKEY = 58  # 58 = CAPS-LOCK
AUTO_DEACTIVATE_AFTER = 60  # seconds or None (default Aim Lab map time is 60 seconds)
_shoot = True
_show_cv2 = True

obs_vc_device_index = -1 # -1 to find by the given name
obs_vc_device_name = "OBS Virtual Camera"

# the bigger these values, the more accurate and fail-safe bot will behave
_pause = 0.05
_shoot_interval = 0.05  # seconds

# used by the script
game_window_rect = WinHelper.GetWindowRect("aimlab_tb", (8, 30, 16, 39))  # cut the borders
game_window_rect = resize_image_to_fit_multiply_of_32(list(game_window_rect))
_ret = None
_aim = False
_activation_time = 0
_correction = [0, 0]

def init_grabber():
    grabber = Grabber()

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


def grab_process(q, stop_event):
    grabber = init_grabber()

    while True:
        try:
            img = grabber.get_image({"left": int(game_window_rect[0]), "top": int(game_window_rect[1]), "width": int(game_window_rect[2]), "height": int(game_window_rect[3])})
        except cv2.error as e:
            logging.error(f'Could not grab the image')
            logging.error(e)
            os._exit(1)

        if img is None:
            continue

        # force only 1 image in the queue (newest)
        # while not q.empty():
        #     q.get_nowait()

        q.put_nowait(img)
        q.join()


def cv2_process(q, stop_event):
    global _aim, _shoot, _ret, _pause, _shoot_interval, _show_cv2, game_window_rect, _activation_time, _correction

    fps = FPS()
    font = cv2.FONT_HERSHEY_SIMPLEX
    _last_shoot = None
    # grabber = init_grabber()
    grabber = MSSGrabber()

    mouse = MouseControls()

    fov = [106.26, 73.74]  # horizontal, vertical

    # x360 = 16364  # x value to rotate on 360 degrees
    x360 = 2727  # x value to rotate on 360 degrees
    x1 = x360/360
    x_full_hor = x1 * fov[0]

    # 2420 = 53.13 grads
    # 360 grads = 16,400 # 16364

    def check_dot(hue_point):
        dot_img = grabber.get_image({"left": int(game_window_rect[0] + (game_window_rect[2]/2) + 5),
                                     "top": int(
                                         game_window_rect[1] + (game_window_rect[3]/2) + 28),
                                     "width": 6,
                                     "height": 6})
        dot_img = cv2.cvtColor(dot_img, cv2.COLOR_BGR2HSV)
        avg_color_per_row = np.average(dot_img, axis=0)
        avg_color = np.average(avg_color_per_row, axis=0)

        # cv2.imshow("test 2", dot_img)

        return (hue_point - 10 < avg_color[0] < hue_point + 20) and (avg_color[1] > 120) and (avg_color[2] > 100)

    while True:
        if not q.empty():
            img = q.get_nowait()
            q.task_done()

            # if _ret is not None:
            #     # return the mouse to base position and proceed again
            #     mouse.move_relative(int(_ret[0]), int(_ret[1]))
            #     _ret = None
            #     # sleep(_pause)
            #     continue

            # some processing code
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

            # detect closest target
            closest = 1000000
            aim_rect = None
            for rect in rectangles:
                x, y, w, h = rect
                mid_x = int((x+(x+w))/2)
                mid_y = int((y+(y+h))/2)
                dist = math.dist([960, 540], [mid_x, mid_y])

                if dist < closest:
                    closest = dist
                    aim_rect = rect

            rectangles = [aim_rect]
            for rect in rectangles:
                x, y, w, h = rect
                if _show_cv2:
                    cv2.rectangle(img, (x, y), (x + w, y + h), [0, 255, 0], 2)

                # shoot
                mid_x = int((x+(x+w))/2)
                mid_y = int((y+(y+h))/2)
                #if _show_cv2:
                #    cv2.circle(img, (mid_x, mid_y), 10, (0, 0, 255), -1)

                if _aim:
                    if _last_shoot is None or time.perf_counter() > (_last_shoot + _shoot_interval):
                        rd_x, rd_y = get_move_angle__new3((mid_x, mid_y), game_window_rect, x1, fov)
                        # rd_x = rd_x / x1
                        # rd_y = rd_y / x1

                        rel_diff = [rd_x, rd_y]
                        rel_diff[0] += _correction[0]
                        rel_diff[1] += _correction[1]

                        print("CORRECTED ANGLES IS", rel_diff)

                        _ret = rel_diff

                        # move the mouse
                        mouse.move_relative(int(x1 * rel_diff[0]), int(x1 * rel_diff[1]))
                        # mouse.move_relative(int(rel_diff[0]), int(rel_diff[1]))
                        sleep(_pause)

                        if _shoot:
                            # detect if aiming the target (more accurate)
                            if check_dot(hue_point):
                                # click
                                mouse.hold_mouse()
                                sleep(0.001)
                                mouse.release_mouse()
                                sleep(0.001)

                                _last_shoot = time.perf_counter()
                                break
                        else:
                            # Aim only once if shoot is disabled
                            _aim = False

                    # Auto deactivate aiming and/or shooting after N seconds
                    if AUTO_DEACTIVATE_AFTER is not None:
                        if _activation_time+AUTO_DEACTIVATE_AFTER < time.perf_counter():
                            _aim = False

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

    qq = multiprocessing.JoinableQueue()
    stop_event = multiprocessing.Event()

    p1 = multiprocessing.Process(target=grab_process, args=(qq, stop_event))
    p2 = multiprocessing.Process(target=cv2_process, args=(qq, stop_event))

    p1.start()
    p2.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping all processes...")
        stop_event.set()
        p1.join()
        p2.join()