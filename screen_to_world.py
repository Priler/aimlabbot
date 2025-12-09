import math


def pixels_to_counts_simple(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    target_x, target_y = target_xy
    screen_width, screen_height = win_wh
    horizontal_fov, vertical_fov = fov_deg_pair

    center_x = screen_width / 2.0
    center_y = screen_height / 2.0

    rel_x = target_x - center_x
    rel_y = target_y - center_y

    normalized_x = rel_x / center_x
    normalized_y = -rel_y / center_y

    half_hfov_rad = math.radians(horizontal_fov / 2.0)
    half_vfov_rad = math.radians(vertical_fov / 2.0)

    horizontal_angle_rad = math.atan(normalized_x * math.tan(half_hfov_rad))
    vertical_angle_rad = math.atan(normalized_y * math.tan(half_vfov_rad))

    horizontal_angle_deg = math.degrees(horizontal_angle_rad)
    vertical_angle_deg = math.degrees(vertical_angle_rad)

    mouse_x = int(round(horizontal_angle_deg * counts_per_deg_x))
    mouse_y = int(round(vertical_angle_deg * counts_per_deg_x))

    return mouse_x, mouse_y


def pixels_to_counts_enhanced(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    target_x, target_y = target_xy
    screen_width, screen_height = win_wh
    horizontal_fov, vertical_fov = fov_deg_pair

    center_x = screen_width / 2.0
    center_y = screen_height / 2.0

    offset_x = target_x - center_x
    offset_y = target_y - center_y

    normalized_offset_x = offset_x / center_x
    normalized_offset_y = offset_y / center_y

    angle_x = math.degrees(math.atan(
        normalized_offset_x * math.tan(math.radians(horizontal_fov / 2))
    ))
    angle_y = math.degrees(math.atan(
        normalized_offset_y * math.tan(math.radians(vertical_fov / 2))
    ))

    mouse_x = int(round(angle_x * counts_per_deg_x))
    mouse_y = int(round(angle_y * counts_per_deg_x))

    return mouse_x, mouse_y


def pixels_to_counts_with_distance_correction(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    mouse_x, mouse_y = pixels_to_counts_simple(target_xy, win_wh, fov_deg_pair, counts_per_deg_x)

    center_x, center_y = win_wh[0] / 2, win_wh[1] / 2
    distance_from_center = math.sqrt(
        (target_xy[0] - center_x) ** 2 + (target_xy[1] - center_y) ** 2
    )
    max_distance = math.sqrt(center_x ** 2 + center_y ** 2)
    distance_ratio = distance_from_center / max_distance

    correction_factor = 1.0 + (distance_ratio * 0.1)

    mouse_x = int(mouse_x * correction_factor)
    mouse_y = int(mouse_y * correction_factor)

    return mouse_x, mouse_y


def pixels_to_counts_single_shot(target_xy, win_wh, fov_deg_pair, counts_per_deg_x, counts_per_deg_y=None):
    w, h = map(float, win_wh)
    cx, cy = w * 0.5, h * 0.5
    dx_pix = float(target_xy[0]) - cx
    dy_pix = float(target_xy[1]) - cy

    hfov = math.radians(fov_deg_pair[0])
    vfov = math.radians(fov_deg_pair[1])
    fx = cx / math.tan(hfov * 0.5)
    fy = cy / math.tan(vfov * 0.5)

    yaw_deg = math.degrees(math.atan2(dx_pix, fx))
    pitch_deg = math.degrees(math.atan2(dy_pix, fy))
    pitch_deg = -pitch_deg

    if counts_per_deg_y is None:
        counts_per_deg_y = counts_per_deg_x

    dx_counts = int(round(counts_per_deg_x * yaw_deg))
    dy_counts = int(round(counts_per_deg_y * pitch_deg))

    return dx_counts, dy_counts


class SensitivityLookupTable:

    def __init__(self, screen_width=1920, screen_height=1080):
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.regions = [
            (0.4, 0.6, 0.4, 0.6, 1.0, 1.0),
            (0.0, 0.2, 0.4, 0.6, 1.05, 1.0),
            (0.2, 0.4, 0.4, 0.6, 1.02, 1.0),
            (0.6, 0.8, 0.4, 0.6, 1.02, 1.0),
            (0.8, 1.0, 0.4, 0.6, 1.05, 1.0),
            (0.4, 0.6, 0.0, 0.2, 1.0, 1.08),
            (0.4, 0.6, 0.2, 0.4, 1.0, 1.03),
            (0.4, 0.6, 0.6, 0.8, 1.0, 1.03),
            (0.4, 0.6, 0.8, 1.0, 1.0, 1.08),
            (0.0, 0.2, 0.0, 0.2, 1.08, 1.10),
            (0.8, 1.0, 0.0, 0.2, 1.08, 1.10),
            (0.0, 0.2, 0.8, 1.0, 1.08, 1.10),
            (0.8, 1.0, 0.8, 1.0, 1.08, 1.10),
        ]

    def get_correction_factor(self, target_xy):
        x_ratio = target_xy[0] / self.screen_width
        y_ratio = target_xy[1] / self.screen_height

        for min_x, max_x, min_y, max_y, x_corr, y_corr in self.regions:
            if min_x <= x_ratio <= max_x and min_y <= y_ratio <= max_y:
                return x_corr, y_corr

        return 1.0, 1.0

    def apply_correction(self, mouse_x, mouse_y, target_xy):
        x_corr, y_corr = self.get_correction_factor(target_xy)
        return int(mouse_x * x_corr), int(mouse_y * y_corr)


def pixels_to_counts_lookup_corrected(target_xy, win_wh, fov_deg_pair, counts_per_deg_x, lookup_table):
    mouse_x, mouse_y = pixels_to_counts_simple(target_xy, win_wh, fov_deg_pair, counts_per_deg_x)
    return lookup_table.apply_correction(mouse_x, mouse_y, target_xy)


def get_angles(aim_target, window_size, fov):
    fov_rad = (math.radians(fov[0]), math.radians(fov[1]))

    x_pos = aim_target[0] / (window_size[0] - 1)
    y_pos = aim_target[1] / (window_size[1] - 1)

    x_angle = math.atan((x_pos - 0.5) * 2 * math.tan(fov_rad[0] / 2))
    y_angle = math.atan((y_pos - 0.5) * 2 * math.tan(fov_rad[1] / 2))

    return math.degrees(x_angle), math.degrees(y_angle)


if __name__ == "__main__":
    WIN_WH = (1920, 1080)
    FOV = (106.26, 73.74)
    COUNTS_PER_DEG = 2727 / 360.0

    target = (860, 540)

    print("Testing different methods:")
    print(f"Target: {target} (center is {WIN_WH[0] / 2}, {WIN_WH[1] / 2})")
    print()

    dx1, dy1 = pixels_to_counts_simple(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Simple: ({dx1}, {dy1})")

    dx2, dy2 = pixels_to_counts_enhanced(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Enhanced: ({dx2}, {dy2})")

    dx3, dy3 = pixels_to_counts_with_distance_correction(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Distance corrected: ({dx3}, {dy3})")

    dx4, dy4 = pixels_to_counts_single_shot(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Single shot: ({dx4}, {dy4})")
