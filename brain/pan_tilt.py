#!/usr/bin/env python3
"""
Control Rambabu's camera pan-tilt servos (one-shot).

Moves the camera to a new angle using the PCA9685 I2C servo driver,
waits for the servo to settle, then kills the PWM signal (jitter-free hold).

Usage:
    uv run python brain/pan_tilt.py pan left [degrees]
    uv run python brain/pan_tilt.py pan right [degrees]
    uv run python brain/pan_tilt.py tilt up [degrees]
    uv run python brain/pan_tilt.py tilt down [degrees]
    uv run python brain/pan_tilt.py center
    uv run python brain/pan_tilt.py angles

Degrees defaults to 20 if not supplied.
"""

import argparse
import logging
import sys

sys.path.insert(0, "/home/rambabu/rambabu_rc")

from lib.pan_tilt import PanTilt

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pan_tilt")

DEFAULT_DEGREES = 20


def main() -> None:
    parser = argparse.ArgumentParser(description="Move Rambabu's camera pan-tilt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pan left / pan right
    pan_parser = subparsers.add_parser("pan", help="Pan camera left or right")
    pan_parser.add_argument("direction", choices=["left", "right"])
    pan_parser.add_argument(
        "degrees",
        type=int,
        nargs="?",
        default=DEFAULT_DEGREES,
        help=f"Degrees to pan (default {DEFAULT_DEGREES})",
    )

    # tilt up / tilt down
    tilt_parser = subparsers.add_parser("tilt", help="Tilt camera up or down")
    tilt_parser.add_argument("direction", choices=["up", "down"])
    tilt_parser.add_argument(
        "degrees",
        type=int,
        nargs="?",
        default=DEFAULT_DEGREES,
        help=f"Degrees to tilt (default {DEFAULT_DEGREES})",
    )

    # center
    subparsers.add_parser("center", help="Return camera to center position")

    # angles
    subparsers.add_parser("angles", help="Print current pan/tilt angles and exit")

    args = parser.parse_args()

    pt: PanTilt | None = None
    result: dict = {}
    try:
        pt = PanTilt()

        if args.command == "pan":
            if args.direction == "left":
                result = pt.pan_left(args.degrees)
            else:
                result = pt.pan_right(args.degrees)

        elif args.command == "tilt":
            if args.direction == "up":
                result = pt.tilt_up(args.degrees)
            else:
                result = pt.tilt_down(args.degrees)

        elif args.command == "center":
            result = pt.center()

        elif args.command == "angles":
            result = pt.get_angles()

    except Exception as exc:
        logger.exception(f"Pan-tilt command failed: {exc}")
        result = {"status": "error", "message": str(exc)}
        sys.exit(1)
    finally:
        if pt is not None:
            try:
                pt.cleanup()
            except Exception as exc:
                logger.warning(f"Pan-tilt cleanup: {exc}")

    print(result)


if __name__ == "__main__":
    main()
