"""Send animated dummy right-hand skeleton via UDP.

Usage:
    python send_dummy_hand.py --target-ip 127.0.0.1 --port 5005 --rate 30
"""

import argparse
import math
import socket
import time

from protocol import pack_right_hand_packet

# ---------------------------------------------------------------------------
# Base pose – right hand, palm facing viewer, fingers pointing up (+Y)
# Coordinates are roughly in a unit box; scaled by the receiver's --scale.
# ---------------------------------------------------------------------------
BASE_HAND = [
    # wrist
    [ 0.00,  0.00,  0.00],
    # thumb (extends right + up)
    [ 0.30,  0.15, -0.10],
    [ 0.50,  0.40, -0.14],
    [ 0.65,  0.70, -0.17],
    [ 0.75,  1.00, -0.20],
    # index (up, right of centre)
    [ 0.18,  0.12,  0.12],
    [ 0.22,  0.70,  0.16],
    [ 0.23,  1.20,  0.18],
    [ 0.21,  1.70,  0.20],
    # middle (up, centre)
    [ 0.00,  0.12,  0.12],
    [ 0.00,  0.75,  0.16],
    [ 0.00,  1.30,  0.18],
    [ 0.00,  1.80,  0.20],
    # ring (up, left of centre)
    [-0.18,  0.10,  0.10],
    [-0.22,  0.65,  0.14],
    [-0.24,  1.10,  0.16],
    [-0.26,  1.50,  0.17],
    # pinky (up, far left)
    [-0.32,  0.06,  0.06],
    [-0.40,  0.50,  0.09],
    [-0.46,  0.85,  0.11],
    [-0.50,  1.15,  0.12],
]


def animate_hand(base, t):
    """Return a new 21×3 list with subtle sinusoidal finger motion."""
    animated = []
    for i, (bx, by, bz) in enumerate(base):
        finger = i // 4 if i > 0 else 0         # 0=wrist, 1=thumb, 2=index, …
        joint_in_finger = (i - 1) % 4 if i > 0 else 0  # 0=base, 3=tip
        freq = 1.8 + finger * 0.35
        phase = finger * 1.2 + joint_in_finger * 0.4
        amp = 0.012 * (1 + joint_in_finger * 1.8)  # tips move more
        dx = amp * math.sin(t * freq + phase)
        dy = amp * math.cos(t * freq * 1.3 + phase + 0.5)
        dz = amp * math.sin(t * freq * 0.7 + phase - 0.3) * 0.5
        animated.append([bx + dx, by + dy, bz + dz])
    return animated


def main():
    parser = argparse.ArgumentParser(description="Send dummy right-hand skeleton via UDP")
    parser.add_argument("--target-ip", default="127.0.0.1", help="Receiver IP")
    parser.add_argument("--port", type=int, default=5005, help="Receiver port")
    parser.add_argument("--rate", type=int, default=30, help="Packets per second")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    period = 1.0 / max(args.rate, 1)
    frame_id = 0
    start = time.time()

    print(f"Sending dummy right-hand to {args.target_ip}:{args.port} @ {args.rate} Hz")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            now = time.time()
            t = now - start
            joints = animate_hand(BASE_HAND, t)
            pkt = pack_right_hand_packet(joints, frame_id)
            sock.sendto(pkt, (args.target_ip, args.port))
            frame_id = (frame_id + 1) & 0xFFFFFFFF

            elapsed = time.time() - now
            sleep_for = period - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
