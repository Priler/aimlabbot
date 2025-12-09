from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple


# Config for capture region
@dataclass
class CaptureRegion:
    left: int = 0
    top: int = 0
    width: int = 1920
    height: int = 1080

    def to_dict(self) -> Dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.width, self.height)


# Config for OBS Virtual Camera grabber
@dataclass
class OBSConfig:
    device_index: int = -1
    device_name: str = "OBS Virtual Camera"


# Main application configuration
@dataclass
class AppConfig:
    window_title: str = ""
    activation_hotkey: int = 58
    show_preview: bool = True
    preview_size: Tuple[int, int] = (1280, 720)
    exit_on_error: bool = True

    grabber_type: str = "mss"
    grabber_options: Dict[str, Any] = field(default_factory=dict)

    capture_region: CaptureRegion = field(default_factory=CaptureRegion)
    border_offsets: Tuple[int, int, int, int] = (0, 0, 0, 0)

    obs: Optional[OBSConfig] = None


def round_to_multiple(number: int, multiple: int) -> int:
    return multiple * round(number / multiple)


def adjust_region_to_multiple(region: CaptureRegion, multiple: int = 32) -> CaptureRegion:
    return CaptureRegion(
        left=region.left,
        top=region.top,
        width=round_to_multiple(region.width, multiple),
        height=round_to_multiple(region.height, multiple),
    )
