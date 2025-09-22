"""Utility script for automating Onmyoji (阴阳师) battles with PyAutoGUI.

The script watches for configured UI elements (png screenshots) on the
screen, adds random delays and click offsets, and clicks the matching
elements to simulate human behaviour. Edit `targets.json` to describe
the UI elements you wish to automate.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    import pyautogui  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime safeguard
    raise SystemExit(
        "PyAutoGUI is required. Install it with 'pip install pyautogui opencv-python'."
    ) from exc


Region = Tuple[int, int, int, int]
Range = Tuple[float, float]


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


def random_point_within_region(box: Tuple[int, int, int, int], margin: int) -> Tuple[int, int]:
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

    # randint expects integers and includes endpoints.
    return random.randint(int(min_x), int(max_x)), random.randint(int(min_y), int(max_y))


def choose_random(range_pair: Range) -> float:
    return random.uniform(*range_pair)


def perform_click(target: Target, box: Tuple[int, int, int, int]) -> None:
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
                box = pyautogui.locateOnScreen(
                    str(target.image_path),
                    confidence=confidence_override or target.confidence,
                    region=target.search_region,
                )
                if box:
                    normalized_box = (box.left, box.top, box.width, box.height)
                    print(f"[+] Detected '{target.name}' at {normalized_box} -> clicking")
                    perform_click(target, normalized_box)
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
