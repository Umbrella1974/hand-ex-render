"""Bridge: Apple Vision Pro hand data → 21×3 UDP skeleton stream.

Supports two input modes:
  1. --npy <file>   replay a recorded data.npy (offline test)
  2. --live <IP>    connect to VisionProStreamer (requires avp_stream)

The Vision Pro delivers:
  right_fingers  (25, 4, 4)  25 bone-indexed 4×4 homogeneous matrices
  right_wrist    (1, 4, 4)   wrist pose in world frame

Each 4×4 matrix encodes the bone's transform; the translation component
(matrix[:3, 3]) gives the joint position in metres.

Coordinate system (ARKit):
  X  →  fingertips direction (fingers point roughly −X)
  Y  →  lateral across palm
  Z  →  up

We remap so the viewer's default xy projection shows fingers pointing up.
"""

import argparse
import socket
import time

import numpy as np

from protocol import pack_right_hand_packet, N_JOINTS, N_DIMS

# ---------------------------------------------------------------------------
# Default 25 → 21 mapping
#
# Vision Pro 25-bone layout (ARKit hand skeleton):
#   0  = palm reference (identity / wrist-anchored origin)
#   1– 4  = thumb:  CMC, MCP, IP, Tip                           (4)
#   5– 9  = index:  metacarpal, MCP, PIP, DIP, Tip              (5)
#   10–14 = middle: metacarpal, MCP, PIP, DIP, Tip              (5)
#   15–19 = ring:   metacarpal, MCP, PIP, DIP, Tip              (5)
#   20–24 = pinky:  metacarpal, MCP, PIP, DIP, Tip              (5)
#
# MediaPipe 21-point order:
#   0 = wrist, 1-4 thumb, 5-8 index, 9-12 middle,
#   13-16 ring, 17-20 pinky
#
# For non-thumb fingers we skip the "metacarpal" entry (first of the five)
# because MediaPipe doesn't separate it from the palm.
# ---------------------------------------------------------------------------
VP_TO_MP = [
    0,                          #  0  VP palm  → MP 0  wrist
    1, 2, 3, 4,                 #  1-4  thumb (direct)
    6, 7, 8, 9,                 #  5-8  index (skip VP 5 metacarpal)
    11, 12, 13, 14,             #  9-12 middle (skip VP 10)
    16, 17, 18, 19,             # 13-16 ring   (skip VP 15)
    21, 22, 23, 24,             # 17-20 pinky  (skip VP 20)
]

# ARKit → viewer coordinate transform
#   VP  X (finger dir)  →  viewer −Y   (so +Y = fingertips up)
#   VP  Y (lateral)     →  viewer  X
#   VP  Z (up)          →  viewer  Z
ARKIT_TO_VIEWER = np.array([
    [ 0, 1, 0],   # new_x = VP_y
    [-1, 0, 0],   # new_y = -VP_x
    [ 0, 0, 1],   # new_z = VP_z
], dtype=np.float64)


def extract_positions(fingers_25x4x4):
    """Extract XYZ from the last column of each 4×4 matrix.

    Args:
        fingers_25x4x4: ndarray of shape (25, 4, 4), float64.

    Returns:
        ndarray of shape (25, 3), float32 — positions in ARKit coords.
    """
    return fingers_25x4x4[:, :3, 3].astype(np.float32)


def convert_to_viewer(positions_25x3, wrist_4x4=None):
    """Map 25 VP positions → MediaPipe 21 points, convert to viewer coords.

    Args:
        positions_25x3: ndarray (25, 3) of joint positions (ARKit frame).
        wrist_4x4: optional ndarray (1, 4, 4) wrist world pose.
                   If provided, wrist world position is used as MP point 0
                   (overriding the palm-relative VP[0]).

    Returns:
        ndarray of shape (21, 3), float32, in viewer coordinate frame.
    """
    # 25 → 21 index mapping
    mp = positions_25x3[VP_TO_MP].copy()  # (21, 3)

    # Optionally replace wrist with absolute world position,
    # and subtract it from all points so the hand stays centred.
    if wrist_4x4 is not None:
        wrist_pos = wrist_4x4[0, :3, 3].astype(np.float32)
        mp[0] = wrist_pos
        mp -= wrist_pos                     # centre on wrist

    # ARKit → viewer axes
    mp = mp @ ARKIT_TO_VIEWER.T

    return mp.astype(np.float32)


def load_npy(path):
    """Load a VisionPro_Teleop data.npy file and return the first frame."""
    data = np.load(path, allow_pickle=True).item()
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Vision Pro hand → 21×3 UDP bridge")
    parser.add_argument("--target-ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--rate", type=int, default=30)

    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--npy", help="Path to recorded data.npy for offline replay")
    src.add_argument("--live", help="Vision Pro IP address (requires avp_stream)")

    parser.add_argument("--loop", action="store_true",
                        help="Loop .npy replay continuously")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    period = 1.0 / max(args.rate, 1)
    frame_id = 0

    # ------------------------------------------------------------------
    # Offline .npy replay
    # ------------------------------------------------------------------
    if args.npy:
        print(f"Loading {args.npy} …")
        data = load_npy(args.npy)
        # data is a dict with keys: right_fingers, right_wrist, left_fingers, ...
        # Each value is (T, …) — a time sequence. Grab T.
        rf = data["right_fingers"]          # (T, 25, 4, 4)
        rw = data.get("right_wrist")        # (T, 1, 4, 4) or None
        n_frames = rf.shape[0]
        print(f"Loaded {n_frames} frames; sending to {args.target_ip}:{args.port}")

        try:
            while True:
                for t in range(n_frames):
                    pos = extract_positions(rf[t])
                    w = rw[t] if rw is not None else None
                    joints = convert_to_viewer(pos, w)
                    pkt = pack_right_hand_packet(joints, frame_id)
                    sock.sendto(pkt, (args.target_ip, args.port))
                    frame_id = (frame_id + 1) & 0xFFFFFFFF

                    elapsed = time.time() % period  # rough pacing
                    if elapsed < period:
                        time.sleep(period - elapsed)

                if not args.loop:
                    print("Replay finished.")
                    break
                print("Looping …")
        except KeyboardInterrupt:
            print("\nStopped.")

    # ------------------------------------------------------------------
    # Live VisionProStreamer
    # ------------------------------------------------------------------
    else:
        try:
            from avp_stream import VisionProStreamer
        except ImportError:
            print("avp_stream not installed.  pip install avp_stream")
            sock.close()
            return

        streamer = VisionProStreamer(ip=args.live, record=False)
        print(f"Connected to Vision Pro at {args.live}")
        print(f"Sending to {args.target_ip}:{args.port} @ {args.rate} Hz")

        try:
            while True:
                latest = streamer.latest
                if latest is not None:
                    pos = extract_positions(latest["right_fingers"])
                    w = latest.get("right_wrist")
                    joints = convert_to_viewer(pos, w)
                    pkt = pack_right_hand_packet(joints, frame_id)
                    sock.sendto(pkt, (args.target_ip, args.port))
                    frame_id = (frame_id + 1) & 0xFFFFFFFF
                time.sleep(period)
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            sock.close()


if __name__ == "__main__":
    main()
