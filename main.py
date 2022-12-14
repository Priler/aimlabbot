import math

from utils.grabbers.mss import Grabber
from utils.fps import FPS
import cv2
import multiprocessing
import numpy as np
from utils.nms import non_max_suppression_fast
from utils.cv2 import filter_rectangles

from utils.controls.mouse.win32 import MouseControls
from utils.win32 import WinHelper
import keyboard

import time
from utils.time import sleep

from screen_to_world import get_move_angle

_aim_n_shoot = False
_ret = None
_show_cv2 = False

# the bigger these values, the more accurate and fail-safe bot will behave
_pause = 0.05
_shoot_interval = 0.05  # seconds

def grab_process(q):
    grabber = Grabber()

    while True:
        img = grabber.get_image({"left": 760, "top": 191, "width": 1920, "height": 1080})

        if img is None:
            continue

        q.put_nowait(img)
        q.join()


def cv2_process(q):
    global _aim_n_shoot, _ret, _pause, _shoot_interval, _show_cv2

    fps = FPS()
    font = cv2.FONT_HERSHEY_SIMPLEX
    _last_shoot = None
    grabber = Grabber()

    mouse = MouseControls()
    game_window_rect = WinHelper.GetWindowRect("aimlab_tb")
    cursor_pos = mouse.get_position()

    fov = [106.26, 73.74]  # horizontal, vertical

    x360 = 16364  # x value to rotate on 360 degrees
    x1 = x360/360
    x_full_hor = x1 * fov[0]

    # 2420 = 53.13 grads
    # 360 grads = 16,400 # 16364

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
                if _show_cv2:
                    cv2.circle(img, (mid_x, mid_y), 10, (0, 0, 255), -1)

                if _aim_n_shoot:
                    if _last_shoot is None or time.perf_counter() > (_last_shoot + _shoot_interval):
                        rel_diff = get_move_angle((mid_x, mid_y), game_window_rect, x1, fov)

                        # move the mouse
                        mouse.move_relative(int(rel_diff[0]), int(rel_diff[1]))
                        sleep(_pause)

                        # detect if aiming the target (more accuracy)
                        dot_img = grabber.get_image({"left": 1734 - 25, "top": 743 - 23, "width": 25, "height": 25})
                        dot_img = cv2.cvtColor(dot_img, cv2.COLOR_BGR2HSV)
                        avg_color_per_row = np.average(dot_img, axis=0)
                        avg_color = np.average(avg_color_per_row, axis=0)

                        if (hue_point - 10 < avg_color[0] < hue_point + 20) \
                                and (avg_color[1] > 120) and (avg_color[2] > 100):
                            # click
                            mouse.hold_mouse()
                            sleep(0.001)
                            mouse.release_mouse()
                            sleep(0.001)

                            _last_shoot = time.perf_counter()
                            break

            # cv stuff
            # img = mask
            if _show_cv2:
                img = cv2.putText(img, f"{fps():.2f} | targets = {targets_count}", (20, 120), font,
                                  1.7, (0, 255, 0), 7, cv2.LINE_AA)
                img = cv2.resize(img, (1280, 720))
                # cv2.imshow("test", cv2.cvtColor(img, cv2.COLOR_RGB2BGRA))
                # mask = cv2.resize(mask, (1280, 720))
                cv2.imshow("test", img)
                cv2.waitKey(1)


def switch_shoot_state(triggered, hotkey):
    global _aim_n_shoot, _ret
    _aim_n_shoot = not _aim_n_shoot  # inverse value

    if not _aim_n_shoot:
        _ret = None


keyboard.add_hotkey(58, switch_shoot_state, args=('triggered', 'hotkey'))

if __name__ == "__main__":

    q = multiprocessing.JoinableQueue()

    p1 = multiprocessing.Process(target=grab_process, args=(q,))
    p2 = multiprocessing.Process(target=cv2_process, args=(q,))

    p1.start()
    p2.start()
