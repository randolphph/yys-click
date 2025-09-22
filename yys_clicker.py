"""Utility script for automating Onmyoji (阴阳师) battles with PyAutoGUI.

The script watches for configured UI elements (PNG screenshots) on the
screen, adds random delays and click offsets, and clicks the matching
elements to simulate human behaviour. Screenshot-based template matching
is performed with Pillow + OpenCV. Edit `targets.json` to describe the UI
elements you wish to automate.

Example usage::

    python yys_clicker.py --targets targets.json

Press Ctrl+C at any time to stop the automation.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    import pyautogui  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime safeguard
    missing = getattr(exc, "name", "pyautogui")
    raise SystemExit(
        "Missing dependency '{missing}'. Install it with 'pip install pyautogui pyscreeze pillow opencv-python'.".format(
            missing=missing
        )
    ) from exc

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - runtime safeguard
    raise SystemExit("NumPy is required. Install it with 'pip install numpy'.") from exc

try:
    import cv2  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime safeguard
    raise SystemExit("OpenCV is required. Install it with 'pip install opencv-python'.") from exc

try:
    from PIL import ImageGrab
except ImportError as exc:  # pragma: no cover - runtime safeguard
    raise SystemExit("Pillow is required for screen capture. Install it with 'pip install pillow'.") from exc

Region = Tuple[int, int, int, int]
Range = Tuple[float, float]
BoundingBox = Tuple[int, int, int, int]


@dataclass
class Target:
    """Template describing the button or area we want to click."""

    name: str
    image_path: Path
    confidence: float = 0.85
    search_region: Optional[Region] = None
    click_margin: int = 6
    move_duration_range: Range = (0.3, 0.7)
    pre_click_delay_range: Range = (0.1, 0.4)
    post_click_delay_range: Range = (0.6, 1.2)

    template: np.ndarray = field(init=False, repr=False)
    template_height: int = field(init=False, repr=False)
    template_width: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._load_template()

    @classmethod
    def from_mapping(cls, base_dir: Path, raw: dict) -> "Target":
        try:
            name = raw["name"]
            image = raw["image"]
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(f"Target definition missing key: {missing}") from exc

        image_path = (base_dir / image).expanduser()
        if not image_path.exists():
            raise ValueError(f"Image file not found: {image_path}")

        target = cls(
            name=name,
            image_path=image_path,
            confidence=float(raw.get("confidence", cls.confidence)),
            search_region=_parse_region(raw.get("region")),
            click_margin=int(raw.get("click_margin", cls.click_margin)),
            move_duration_range=_parse_range(
                raw.get("move_duration_range", cls.move_duration_range),
                fallback=cls.move_duration_range,
            ),
            pre_click_delay_range=_parse_range(
                raw.get("pre_click_delay_range", cls.pre_click_delay_range),
                fallback=cls.pre_click_delay_range,
            ),
            post_click_delay_range=_parse_range(
                raw.get("post_click_delay_range", cls.post_click_delay_range),
                fallback=cls.post_click_delay_range,
            ),
        )
        return target

    def _load_template(self) -> None:
        image_bgr = cv2.imread(str(self.image_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise ValueError(f"Failed to read image file: {self.image_path}")
        template_gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        if template_gray.size == 0:
            raise ValueError(f"Template image is empty: {self.image_path}")
        self.template = template_gray
        self.template_height, self.template_width = template_gray.shape[:2]


def _parse_region(value) -> Optional[Region]:
    if value is None:
        return None
    if not isinstance(value, Sequence) or len(value) != 4:
        raise ValueError("Region must be a sequence of four integers: left, top, width, height")
    left, top, width, height = map(int, value)
    return left, top, width, height


def _parse_range(value, fallback: Range) -> Range:
    if value is None:
        return fallback
    if isinstance(value, tuple):
        low, high = value
    else:
        if not isinstance(value, Sequence) or len(value) != 2:
            raise ValueError("Ranges must contain two numeric values: min, max")
        low, high = value
    low = float(low)
    high = float(high)
    if low > high:
        raise ValueError(f"Invalid range: min {low} is greater than max {high}")
    return low, high


def load_targets(path: Path) -> List[Target]:
    raw_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        raise ValueError("Target configuration must be a JSON array")

    base_dir = path.parent
    targets: List[Target] = []
    for item in raw_data:
        if not isinstance(item, dict):
            raise ValueError("Each target must be a JSON object")
        targets.append(Target.from_mapping(base_dir, item))
    return targets


def capture_screen(region: Optional[Region]) -> np.ndarray:
    if region is None:
        bbox = None
    else:
        left, top, width, height = region
        bbox = (left, top, left + width, top + height)
    screenshot = ImageGrab.grab(bbox=bbox)
    frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    return frame


def locate_target(target: Target, confidence: float) -> Optional[BoundingBox]:
    search_image = capture_screen(target.search_region)
    if (
        search_image.shape[0] < target.template_height
        or search_image.shape[1] < target.template_width
    ):
        return None

    result = cv2.matchTemplate(search_image, target.template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < confidence:
        return None

    offset_x = target.search_region[0] if target.search_region else 0
    offset_y = target.search_region[1] if target.search_region else 0
    left = offset_x + int(max_loc[0])
    top = offset_y + int(max_loc[1])
    return left, top, target.template_width, target.template_height


def random_point_within_region(box: BoundingBox, margin: int) -> Tuple[int, int]:
    left, top, width, height = box
    width = max(width, 1)
    height = max(height, 1)

    effective_margin_x = min(margin, max(width // 2 - 1, 0))
    effective_margin_y = min(margin, max(height // 2 - 1, 0))

    min_x = left + effective_margin_x
    max_x = left + width - effective_margin_x
    min_y = top + effective_margin_y
    max_y = top + height - effective_margin_y

    if min_x >= max_x:
        min_x, max_x = left, left + width
    if min_y >= max_y:
        min_y, max_y = top, top + height

    return random.randint(int(min_x), int(max_x)), random.randint(int(min_y), int(max_y))


def choose_random(range_pair: Range) -> float:
    return random.uniform(*range_pair)


def perform_click(target: Target, box: BoundingBox) -> None:
    x, y = random_point_within_region(box, target.click_margin)

    move_duration = choose_random(target.move_duration_range)
    pyautogui.moveTo(x, y, duration=move_duration)

    time.sleep(choose_random(target.pre_click_delay_range))
    pyautogui.click(x, y)
    time.sleep(choose_random(target.post_click_delay_range))


def run(targets: Sequence[Target], scan_interval: Range, confidence_override: Optional[float]) -> None:
    pyautogui.FAILSAFE = True
    print("Starting Onmyoji automation. Move mouse to top-left corner to abort instantly.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            for target in targets:
                threshold = confidence_override or target.confidence
                box = locate_target(target, threshold)
                if box:
                    print(f"[+] Detected '{target.name}' at {box} (score >= {threshold}) -> clicking")
                    perform_click(target, box)
                    break
            else:
                idle_delay = choose_random(scan_interval)
                time.sleep(idle_delay)
    except KeyboardInterrupt:
        print("\nStopped by user.")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Onmyoji auto-battle clicker")
    parser.add_argument(
        "--targets",
        type=Path,
        default=Path("targets.json"),
        help="Path to targets configuration JSON file",
    )
    parser.add_argument(
        "--scan-interval",
        type=float,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=(0.3, 0.6),
        help="Random delay range (seconds) between screen scans when nothing is found.",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="Override confidence for all targets (0-1). Uses per-target value if omitted.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        targets = load_targets(args.targets)
    except FileNotFoundError:
        print(
            f"Target configuration not found: {args.targets}. Create it based on targets.example.json",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if not targets:
        print("No targets configured. Add entries to the JSON file before running.", file=sys.stderr)
        return 2

    scan_interval = _parse_range(args.scan_interval, (0.3, 0.6))
    if args.confidence is not None and not 0.0 < args.confidence <= 1.0:
        print("Confidence must be in (0, 1].", file=sys.stderr)
        return 2

    run(targets, scan_interval, args.confidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
