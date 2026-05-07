"""Send animated dummy hand skeleton via UDP — Vision Pro 25-point format.

Generates (25, 4, 4) homogeneous matrices in ARKit coordinates, then
converts through the same pipeline used by send_vision_pro_hand.py so the
full VP → 21×3 chain is testable without hardware.

Usage:
    python send_dummy_hand.py --target-ip 127.0.0.1 --port 5005 --rate 30
"""

import argparse
import math
import socket
import time

import numpy as np

from protocol import pack_right_hand_packet
from send_vision_pro_hand import extract_positions, convert_to_viewer

# ---------------------------------------------------------------------------
# Base hand in ARKit coordinates (VP conventions)
#   X  = finger direction  (fingers point −X)
#   Y  = lateral           (thumb side = +Y)
#   Z  = up
# All positions relative to palm at origin.  Units: metres.
# ---------------------------------------------------------------------------
BASE_VP_25 = np.array([
    #  0  palm / wrist reference
    [ 0.00,  0.00,  0.00],
    #  1– 4  thumb (CMC → MCP → IP → tip)
    [-0.02,  0.030, -0.010],
    [-0.04,  0.050, -0.020],
    [-0.06,  0.068, -0.025],
    [-0.08,  0.082, -0.028],
    #  5– 9  index (metacarpal → MCP → PIP → DIP → tip)
    [-0.02,  0.012,  0.015],
    [-0.04,  0.012,  0.035],
    [-0.07,  0.012,  0.058],
    [-0.09,  0.012,  0.072],
    [-0.11,  0.012,  0.085],
    # 10–14  middle
    [-0.02,  0.000,  0.020],
    [-0.04,  0.000,  0.045],
    [-0.07,  0.000,  0.070],
    [-0.10,  0.000,  0.085],
    [-0.12,  0.000,  0.100],
    # 15–19  ring
    [-0.02, -0.012,  0.015],
    [-0.04, -0.012,  0.035],
    [-0.06, -0.012,  0.055],
    [-0.08, -0.012,  0.068],
    [-0.10, -0.012,  0.078],
    # 20–24  pinky
    [-0.02, -0.025,  0.010],
    [-0.03, -0.030,  0.025],
    [-0.05, -0.038,  0.040],
    [-0.07, -0.045,  0.050],
    [-0.08, -0.050,  0.058],
], dtype=np.float64)


def animate_vp_hand(base, t):
    """Add subtle sinusoidal motion.  Returns (25, 4, 4) ndarray."""
    animated = base.copy()
    for i in range(25):
        if i == 0:
            finger_id, seg = 0, 0
        else:
            finger_id = (i - 1) // 5 + 1   # 1=thumb … 5=pinky
            seg = (i - 1) % 5
        freq = 2.0 + finger_id * 0.4
        phase = finger_id * 1.5 + seg * 0.5
        amp = 0.0025 * (1 + seg * 0.7)
        animated[i, 0] += amp * math.sin(t * freq + phase)
        animated[i, 1] += amp * math.cos(t * freq * 1.3 + phase + 0.5) * 0.5
        animated[i, 2] += amp * math.sin(t * freq * 0.7 + phase - 0.3) * 0.5

    # Build (25, 4, 4) homogeneous matrices
    mats = np.zeros((25, 4, 4), dtype=np.float64)
    mats[:, 3, 3] = 1.0
    mats[:, :3, 3] = animated
    # identity rotation (3×3)
    mats[:, 0, 0] = 1.0
    mats[:, 1, 1] = 1.0
    mats[:, 2, 2] = 1.0
    return mats


def main():
    parser = argparse.ArgumentParser(
        description="Send dummy VP-format hand skeleton via UDP")
    parser.add_argument("--target-ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--rate", type=int, default=30)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    period = 1.0 / max(args.rate, 1)
    frame_id = 0
    start = time.time()

    print(f"Sending dummy VP-format hand to {args.target_ip}:{args.port} "
          f"@ {args.rate} Hz")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            loop_start = time.time()
            t = loop_start - start
            mats = animate_vp_hand(BASE_VP_25, t)         # (25, 4, 4)
            pos = extract_positions(mats)                  # (25, 3)
            joints = convert_to_viewer(pos)                # (21, 3) viewer coords
            pkt = pack_right_hand_packet(joints, frame_id)
            sock.sendto(pkt, (args.target_ip, args.port))
            frame_id = (frame_id + 1) & 0xFFFFFFFF

            elapsed = time.time() - loop_start
            sleep_for = period - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
