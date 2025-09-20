import math

def pixels_to_counts_simple(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    """
    Simple, accurate single-step conversion using proper perspective math.
    """
    target_x, target_y = target_xy
    screen_width, screen_height = win_wh
    horizontal_fov, vertical_fov = fov_deg_pair
    
    center_x = screen_width / 2.0
    center_y = screen_height / 2.0
    
    # Calculate relative position from center
    rel_x = target_x - center_x
    rel_y = target_y - center_y
    
    # Convert to normalized coordinates [-1, 1]
    normalized_x = rel_x / center_x
    normalized_y = -rel_y / center_y  # Negative for screen Y flip
    
    # Calculate angles using proper perspective projection
    half_hfov_rad = math.radians(horizontal_fov / 2.0)
    half_vfov_rad = math.radians(vertical_fov / 2.0)
    
    horizontal_angle_rad = math.atan(normalized_x * math.tan(half_hfov_rad))
    vertical_angle_rad = math.atan(normalized_y * math.tan(half_vfov_rad))
    
    # Convert to degrees
    horizontal_angle_deg = math.degrees(horizontal_angle_rad)
    vertical_angle_deg = math.degrees(vertical_angle_rad)
    
    # Convert to mouse counts
    mouse_x = int(round(horizontal_angle_deg * counts_per_deg_x))
    mouse_y = int(round(vertical_angle_deg * counts_per_deg_x))  # Use same sensitivity
    
    return mouse_x, mouse_y

# Method 1: Better Calibration
def recalibrate_sensitivity(mouse_controller, screen_center=(960, 540)):
    """
    More accurate calibration method.
    Test multiple angles to get better counts_per_degree value.
    """
    print("=== Sensitivity Calibration ===")
    print("Instructions:")
    print("1. Look at the center of the screen")
    print("2. Press Enter to start each test")
    print("3. Measure how far the crosshair moved")
    print()
    
    test_angles = [10, 30, 45, 90, 180]  # degrees to test
    results = []
    
    for angle in test_angles:
        input(f"Ready to test {angle}° rotation? Press Enter...")
        
        # Calculate mouse movement for this angle
        estimated_counts = int(2727 / 360 * angle)  # Your current estimate
        
        print(f"Moving mouse by {estimated_counts} counts...")
        mouse_controller.move_relative(estimated_counts, 0)
        
        actual_angle = float(input(f"How many degrees did crosshair actually move? "))
        
        if actual_angle > 0:
            actual_counts_per_degree = estimated_counts / actual_angle
            results.append(actual_counts_per_degree)
            print(f"Calculated: {actual_counts_per_degree:.2f} counts/degree")
        
        # Return to center
        mouse_controller.move_relative(-estimated_counts, 0)
        print()
    
    if results:
        avg_counts_per_degree = sum(results) / len(results)
        print(f"Average counts per degree: {avg_counts_per_degree:.2f}")
        return avg_counts_per_degree
    
    return 2727 / 360  # fallback

# Method 2: Distance-Based Correction
def pixels_to_counts_with_distance_correction(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    """
    Apply distance-based correction factors for better accuracy.
    """
    mouse_x, mouse_y = pixels_to_counts_simple(target_xy, win_wh, fov_deg_pair, counts_per_deg_x)
    
    # Calculate distance from center (for correction factor)
    center_x, center_y = win_wh[0] / 2, win_wh[1] / 2
    distance_from_center = math.sqrt((target_xy[0] - center_x)**2 + (target_xy[1] - center_y)**2)
    max_distance = math.sqrt(center_x**2 + center_y**2)  # corner distance
    distance_ratio = distance_from_center / max_distance
    
    # Apply correction based on distance from center
    # Far from center often needs slight boost due to perspective distortion
    correction_factor = 1.0 + (distance_ratio * 0.1)  # 10% boost at corners
    
    mouse_x = int(mouse_x * correction_factor)
    mouse_y = int(mouse_y * correction_factor)
    
    return mouse_x, mouse_y

# Method 3: Lookup Table Approach
class SensitivityLookupTable:
    """
    Create a lookup table of corrections based on screen regions.
    """
    def __init__(self, screen_width=1920, screen_height=1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Correction factors for different screen regions
        # Format: (min_x_ratio, max_x_ratio, min_y_ratio, max_y_ratio, x_correction, y_correction)
        self.regions = [
            # Center region (no correction needed)
            (0.4, 0.6, 0.4, 0.6, 1.0, 1.0),
            
            # Left regions
            (0.0, 0.2, 0.4, 0.6, 1.05, 1.0),  # Far left
            (0.2, 0.4, 0.4, 0.6, 1.02, 1.0),  # Near left
            
            # Right regions  
            (0.6, 0.8, 0.4, 0.6, 1.02, 1.0),  # Near right
            (0.8, 1.0, 0.4, 0.6, 1.05, 1.0),  # Far right
            
            # Top regions
            (0.4, 0.6, 0.0, 0.2, 1.0, 1.08),  # Far top
            (0.4, 0.6, 0.2, 0.4, 1.0, 1.03),  # Near top
            
            # Bottom regions
            (0.4, 0.6, 0.6, 0.8, 1.0, 1.03),  # Near bottom
            (0.4, 0.6, 0.8, 1.0, 1.0, 1.08),  # Far bottom
            
            # Corner regions (need most correction)
            (0.0, 0.2, 0.0, 0.2, 1.08, 1.10),  # Top-left
            (0.8, 1.0, 0.0, 0.2, 1.08, 1.10),  # Top-right
            (0.0, 0.2, 0.8, 1.0, 1.08, 1.10),  # Bottom-left
            (0.8, 1.0, 0.8, 1.0, 1.08, 1.10),  # Bottom-right
        ]
    
    def get_correction_factor(self, target_xy):
        """
        Get correction factors for a specific screen position.
        """
        x_ratio = target_xy[0] / self.screen_width
        y_ratio = target_xy[1] / self.screen_height
        
        for min_x, max_x, min_y, max_y, x_corr, y_corr in self.regions:
            if min_x <= x_ratio <= max_x and min_y <= y_ratio <= max_y:
                return x_corr, y_corr
        
        # Default correction if no region matches
        return 1.0, 1.0
    
    def apply_correction(self, mouse_x, mouse_y, target_xy):
        """
        Apply position-based correction to mouse movement.
        """
        x_corr, y_corr = self.get_correction_factor(target_xy)
        return int(mouse_x * x_corr), int(mouse_y * y_corr)

def pixels_to_counts_lookup_corrected(target_xy, win_wh, fov_deg_pair, counts_per_deg_x, lookup_table):
    """
    Single-step conversion with lookup table corrections.
    """
    mouse_x, mouse_y = pixels_to_counts_simple(target_xy, win_wh, fov_deg_pair, counts_per_deg_x)
    return lookup_table.apply_correction(mouse_x, mouse_y, target_xy)

# Method 4: Fine-tuned FOV approach
def pixels_to_counts_fov_tuned(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    """
    Sometimes the stated FOV isn't exactly right. This tries slight adjustments.
    """
    # Try slight FOV adjustments to see if they improve accuracy
    fov_adjustments = [0.98, 0.99, 1.0, 1.01, 1.02]  # -2% to +2%
    
    results = []
    for adjustment in fov_adjustments:
        adjusted_fov = (fov_deg_pair[0] * adjustment, fov_deg_pair[1] * adjustment)
        mouse_x, mouse_y = pixels_to_counts_simple(target_xy, win_wh, adjusted_fov, counts_per_deg_x)
        results.append((mouse_x, mouse_y, adjustment))
    
    # For now, return the middle value (no adjustment)
    # You could test each and see which gives best results
    return results[2][0], results[2][1]  # 1.0 adjustment

# Method 5: Your enhanced version with better math
def pixels_to_counts_enhanced(target_xy, win_wh, fov_deg_pair, counts_per_deg_x):
    """
    Enhanced version of your current approach with mathematical improvements.
    """
    target_x, target_y = target_xy
    screen_width, screen_height = win_wh
    horizontal_fov, vertical_fov = fov_deg_pair
    
    center_x = screen_width / 2.0
    center_y = screen_height / 2.0
    
    # Calculate pixel offsets from center
    offset_x = target_x - center_x
    offset_y = target_y - center_y
    
    # Convert to angular offsets using proper trigonometry
    # This is more accurate than your linear interpolation
    angle_per_pixel_x = horizontal_fov / screen_width
    angle_per_pixel_y = vertical_fov / screen_height
    
    # Apply perspective correction using atan
    normalized_offset_x = offset_x / center_x
    normalized_offset_y = offset_y / center_y
    
    # Use atan for proper perspective projection
    angle_x = math.degrees(math.atan(normalized_offset_x * math.tan(math.radians(horizontal_fov / 2))))
    angle_y = math.degrees(math.atan(normalized_offset_y * math.tan(math.radians(vertical_fov / 2))))
    
    # Convert to mouse counts
    mouse_x = int(round(angle_x * counts_per_deg_x))
    mouse_y = int(round(angle_y * counts_per_deg_x))
    
    return mouse_x, mouse_y

# Example usage for testing different methods
if __name__ == "__main__":
    # Your parameters
    WIN_WH = (1920, 1080)
    FOV = (106.26, 73.74)
    COUNTS_PER_DEG = 2727 / 360.0
    
    # Test target (example: 100 pixels left of center)
    target = (860, 540)  # 100px left of center
    
    print("Testing different single-step methods:")
    print(f"Target: {target} (center is {WIN_WH[0]/2}, {WIN_WH[1]/2})")
    print()
    
    # Method 1: Simple perspective correction
    dx1, dy1 = pixels_to_counts_simple(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Simple method: ({dx1}, {dy1})")
    
    # Method 2: Distance correction
    dx2, dy2 = pixels_to_counts_with_distance_correction(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Distance corrected: ({dx2}, {dy2})")
    
    # Method 3: Lookup table
    lookup = SensitivityLookupTable()
    dx3, dy3 = pixels_to_counts_lookup_corrected(target, WIN_WH, FOV, COUNTS_PER_DEG, lookup)
    print(f"Lookup corrected: ({dx3}, {dy3})")
    
    # Method 4: Enhanced math
    dx4, dy4 = pixels_to_counts_enhanced(target, WIN_WH, FOV, COUNTS_PER_DEG)
    print(f"Enhanced math: ({dx4}, {dy4})")
    
    print(f"\nFor comparison, your original linear method would give:")
    linear_angle = (FOV[0]/2) * ((target[0] - WIN_WH[0]/2) / WIN_WH[0])
    linear_counts = int(linear_angle * COUNTS_PER_DEG)
    print(f"Linear method: ({linear_counts}, 0)")