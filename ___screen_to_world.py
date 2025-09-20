from math import atan, degrees, radians, tan
import math
from utils.cv2 import point_get_difference


def x_get_ratio(angle):
    if angle < 15:
        return 0.0201
    elif angle < 20:
        return 0.0204
    elif angle < 24.5:
        return 0.0206
    elif angle < 29:
        return 0.0211
    elif angle < 33.5:
        return 0.0216
    elif angle < 35:
        return 0.02175
    elif angle < 39:
        return 0.0214
    elif angle < 45:
        return 0.0212
    elif angle < 49:
        return 0.0214
    else:
        return 0.0216


def y_get_ratio(angle):
    if angle < 6:
        return 0.022
    elif angle < 15:
        return 0.023
    elif angle < 24:
        return 0.0235
    elif angle < 25:
        return 0.0232
    elif angle < 26:
        return 0.0228
    elif angle < 28:
        return 0.0225
    elif angle < 29:
        return 0.0223
    elif angle < 35:
        return 0.022
    elif angle < 40:
        return 0.021


def get_angles(aim_target, window_size, fov):
    """
    Get (x, y) angles from center of image to aim_target.

    Args:
        aim_target: pair of numbers (x, y) where to aim
        window_size: size of area (x, y)
        fov: field of view in degrees, (horizontal, vertical)

    Returns:
       Pair of floating point angles (x, y) in degrees
    """
    fov = (radians(fov[0]), radians(fov[1]))

    x_pos = aim_target[0] / (window_size[0] - 1)
    y_pos = aim_target[1] / (window_size[1] - 1)

    x_angle = atan((x_pos - 0.5) * 2 * tan(fov[0] / 2))
    y_angle = atan((y_pos - 0.5) * 2 * tan(fov[1] / 2))

    return degrees(x_angle), degrees(y_angle)


def get_move_angle(aim_target, gwr, pixels_per_degree, fov):
    angles = get_angles(aim_target, (gwr[2], gwr[3]), fov)

    return list(angles)


def pixels_to_counts_single_shot(target_xy, win_wh, fov_deg_pair, counts_per_deg_x, counts_per_deg_y=None):
    """
    target_xy: (x,y) pixel in the game window (same res as the render capture)
    win_wh: (w,h)
    fov_deg_pair: (HFOV_deg, VFOV_deg) - the game's actual horizontal and vertical FOV
    counts_per_deg_x: x360_x/360.0
    counts_per_deg_y: optional y360_y/360.0; if None, use counts_per_deg_x
    returns: (dx_counts, dy_counts) to pass once to mouse.move_relative
    """
    w, h = map(float, win_wh)
    cx, cy = w*0.5, h*0.5
    dx_pix = float(target_xy[0]) - cx   # right positive
    dy_pix = float(target_xy[1]) - cy   # down positive (screen coords)

    hfov = math.radians(fov_deg_pair[0])
    vfov = math.radians(fov_deg_pair[1])
    fx = cx / math.tan(hfov * 0.5)
    fy = cy / math.tan(vfov * 0.5)

    yaw_deg   = math.degrees(math.atan2(dx_pix, fx))   # +right
    pitch_deg = math.degrees(math.atan2(dy_pix, fy))   # +down (screen)

    # Most games interpret +mouseY as look down. To aim up when target is above,
    # invert pitch once:
    pitch_deg = -pitch_deg

    if counts_per_deg_y is None:
        counts_per_deg_y = counts_per_deg_x

    dx_counts = int(round(counts_per_deg_x * yaw_deg))
    dy_counts = int(round(counts_per_deg_y * pitch_deg))
    return dx_counts, dy_counts


def get_move_angle__single_shot(aim_target_xy, gwr, counts_per_degree, fov_deg_pair):
    """
    aim_target_xy: (x,y) in window pixels
    gwr: [left, top, width, height]  (only width/height are used)
    counts_per_degree: your x1 = x360 / 360
    fov_deg_pair: [hfov_deg, vfov_deg] for the current Aim Lab profile

    returns: (dx_counts, dy_counts) for ONE call to mouse.move_relative
    """
    w = float(gwr[2]); h = float(gwr[3])
    cx = w * 0.5;      cy = h * 0.5

    # Pixel offset from image center (right/down positive)
    dx_pix = float(aim_target_xy[0]) - cx
    dy_pix = float(aim_target_xy[1]) - cy

    # Intrinsics derived from FOV: fx = (w/2) / tan(hfov/2), fy = (h/2) / tan(vfov/2)
    hfov = math.radians(fov_deg_pair[0])
    vfov = math.radians(fov_deg_pair[1])
    fx = cx / math.tan(hfov * 0.5)
    fy = cy / math.tan(vfov * 0.5)

    # Exact angles from pinhole model (atan2 keeps accuracy for large offsets)
    yaw_deg   = math.degrees(math.atan2(dx_pix, fx))  # +right, -left
    pitch_deg = math.degrees(math.atan2(dy_pix, fy))  # +down, -up (screen coords)

    # Most games define mouse +Y as "look down".
    # If your engine expects +pitch = up, flip it once here:
    pitch_deg = -pitch_deg

    # Convert degrees -> mouse counts for a single relative move
    dx_counts = int(round(counts_per_degree * yaw_deg))
    dy_counts = int(round(counts_per_degree * pitch_deg))
    return dx_counts, dy_counts


def get_move_angle__new3(aim_target, gwr, _pixels_per_degree_unused, fov_deg):
    """
    aim_target: (x,y) in window pixels
    gwr: [left, top, width, height]
    fov_deg: [hfov_deg, vfov_deg]  (use your game's real FOV)
    returns: [yaw_deg, pitch_deg] to move (positive yaw = turn right; positive pitch = look up)
    """
    w = float(gwr[2]); h = float(gwr[3])
    cx = w * 0.5;      cy = h * 0.5

    dx = float(aim_target[0]) - cx          # rightward is positive
    dy = float(aim_target[1]) - cy          # downward is positive in screen coords

    hfov = math.radians(fov_deg[0])
    vfov = math.radians(fov_deg[1])

    # Pinhole model: angle = atan( tan(FOV/2) * normalized_offset )
    # normalized_offset = offset_pixels / (half_dimension_pixels)
    yaw_deg   = math.degrees(math.atan(math.tan(hfov * 0.5) * (dx / cx)))
    pitch_deg = math.degrees(math.atan(math.tan(vfov * 0.5) * (dy / cy)))

    # Most games define positive mouse Y as "look down".
    # If your engine needs positive pitch = look up, flip the sign:
    pitch_deg = -pitch_deg

    return [yaw_deg, pitch_deg]


# print(get_angles((321, 378), (1920, 1080), (106.26, 73.74)), "should be around [-41.88894918065101, -8.580429158509922]")
# print(get_move_angle__new3((321, 378), (0, 0, 1920, 1080), 0, (106.26, 73.74)), "should be around [-41.88894918065101, -8.580429158509922]")
# exit(1)


def get_move_angle__new(aim_target, gwr, pixels_per_degree, fov):
    game_window_rect__center = (gwr[2]/2, gwr[3]/2)
    rel_diff = list(point_get_difference(game_window_rect__center, aim_target))

    x_degs = degrees(atan(rel_diff[0]/game_window_rect__center[0])) * ((fov[0]/2)/45)
    y_degs = degrees(atan(rel_diff[1] / game_window_rect__center[0])) * ((fov[1]/2)/45)
    rel_diff[0] = pixels_per_degree * x_degs
    rel_diff[1] = pixels_per_degree * y_degs

    return rel_diff, (x_degs+y_degs)

# get_move_angle__new((900, 540), (0, 0, 1920, 1080), 16364/360, (106.26, 73.74))
# Output will be: ([-191.93420990140876, 0.0], -4.222458785413539)
# But it's not accurate, overall x_degs must be more or less than -4.22...

def get_move_angle(aim_target, gwr, pixels_per_degree, fov):
    game_window_rect__center = (gwr[2]/2, gwr[3]/2)

    # rel_diff = list(point_get_difference(game_window_rect__center, aim_target))  # get absolute offset
    rel_diff = [0, 0]

    if game_window_rect__center[0] > aim_target[0]:
        rel_diff[0] = -1
    else:
        rel_diff[0] = 1

    if game_window_rect__center[1] > aim_target[1]:
        rel_diff[1] = -1
    else:
        rel_diff[1] = 1

    # FOR X (convert to degrees movement
    x_mult_factor = (pixels_per_degree * fov[0] / 2) / game_window_rect__center[0]
    X_CORRECTION_DEGS = 7.2  # 7.2

    x_diff = game_window_rect__center[0] - aim_target[0]
    x_diff_move_factor = x_diff * x_mult_factor
    x_diff__angle = x_diff_move_factor / pixels_per_degree

    if x_diff > game_window_rect__center[0] / 2:
        x_diff_quarter = x_diff - game_window_rect__center[0] / 2
        x_diff__angle_fixed = X_CORRECTION_DEGS - (X_CORRECTION_DEGS * (x_diff_quarter / (game_window_rect__center[0] / 2)))
    else:
        x_diff_quarter = x_diff
        x_diff__angle_fixed = X_CORRECTION_DEGS * (x_diff_quarter / (game_window_rect__center[0] / 2))

    x_diff__angle_move_factor = x_diff__angle + x_diff__angle_fixed
    x_move = x_diff__angle_move_factor / x_get_ratio(x_diff__angle_move_factor)

    if rel_diff[0] < 0:
        rel_diff[0] = -int(abs(x_move))
    else:
        rel_diff[0] = int(abs(x_move))

    # FOR Y (convert to degrees movement
    y_mult_factor = (pixels_per_degree * fov[1] / 2) / game_window_rect__center[1]
    Y_CORRECTION_DEGS = 4.05  # 7.2

    y_diff = game_window_rect__center[1] - aim_target[1]
    y_diff_move_factor = y_diff * y_mult_factor
    y_diff__angle = y_diff_move_factor / pixels_per_degree

    if y_diff > game_window_rect__center[1] / 2:
        y_diff_quarter = y_diff - game_window_rect__center[1] / 2
        y_diff__angle_fixed = Y_CORRECTION_DEGS - (Y_CORRECTION_DEGS * (y_diff_quarter / (game_window_rect__center[1] / 2)))
    else:
        y_diff_quarter = y_diff
        y_diff__angle_fixed = Y_CORRECTION_DEGS * (y_diff_quarter / (game_window_rect__center[1] / 2))

    y_diff__angle_move_factor = y_diff__angle + y_diff__angle_fixed
    y_move = y_diff__angle_move_factor / y_get_ratio(y_diff__angle_move_factor)

    if rel_diff[1] < 0:
        rel_diff[1] = -int(abs(y_move))
    else:
        rel_diff[1] = int(abs(y_move))

    return rel_diff
