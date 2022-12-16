from math import atan, degrees, sqrt
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


def get_move_angle__new(aim_target, gwr, pixels_per_degree, fov, _r=False):
    game_window_rect__center = (gwr[2]/2, gwr[3]/2)
    rel_diff = list(point_get_difference(game_window_rect__center, aim_target))

    x_degs = degrees(atan(rel_diff[0]/game_window_rect__center[0])) * ((fov[0]/2)/45)
    y_degs = degrees(atan(rel_diff[1] / game_window_rect__center[0])) * ((fov[1]/2)/45)
    rel_diff[0] = pixels_per_degree * x_degs
    rel_diff[1] = pixels_per_degree * y_degs

    return rel_diff, (x_degs+y_degs)


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
