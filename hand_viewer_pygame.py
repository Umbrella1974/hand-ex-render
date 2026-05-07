"""Lightweight right-hand skeleton viewer using pygame + UDP.

Usage:
    python hand_viewer_pygame.py --port 5005
    python hand_viewer_pygame.py --low-power --fps 20 --width 640 --height 480
"""

import argparse
import math
import socket
import struct
import sys
import time

import numpy as np
import pygame

from protocol import unpack_right_hand_packet, N_JOINTS

# ---------------------------------------------------------------------------
# Bone connectivity – MediaPipe hand
# ---------------------------------------------------------------------------
HAND_BONES = [
    (0, 1), (1, 2), (2, 3), (3, 4),       # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),       # index
    (0, 9), (9, 10), (10, 11), (11, 12),  # middle
    (0, 13), (13, 14), (14, 15), (15, 16),# ring
    (0, 17), (17, 18), (18, 19), (19, 20),# pinky
    (5, 9), (9, 13), (13, 17), (5, 17),   # palm transversals
]

FINGERTIPS = {4, 8, 12, 16, 20}
PALM_POLY = [0, 5, 9, 13, 17]  # wrist → knuckle row

# ---------------------------------------------------------------------------
# Colours (RGBA / RGB)
# ---------------------------------------------------------------------------
BG_COLOR = (10, 10, 18)
GRID_COLOR = (22, 22, 32)
BONE_GLOW_WIDE = (0, 140, 200, 25)
BONE_GLOW_MID = (0, 180, 240, 70)
BONE_CORE = (0, 210, 255, 210)
BONE_BRIGHT = (160, 230, 255, 255)
BONE_LOW_POWER = (0, 190, 240)
JOINT_RING = (0, 210, 255)
JOINT_TIP = (100, 240, 255)
PALM_FILL = (0, 160, 220, 35)
PALM_LINE = (0, 180, 240, 80)
HUD_TEXT = (180, 200, 220)
WAIT_TEXT = (120, 130, 150)


class HandViewer:
    def __init__(self, args):
        self.listen_ip = args.listen_ip
        self.port = args.port
        self.width = args.width
        self.height = args.height
        self.target_fps = args.fps
        self.scale = args.scale
        self.flip_x = args.flip_x
        self.flip_y = args.flip_y
        self.axis = args.axis
        self.smooth = args.smooth
        self.low_power = args.low_power

        # Socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.listen_ip, self.port))
        self.sock.settimeout(0.001)  # non-blocking poll

        # Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height),
                                              pygame.DOUBLEBUF)
        pygame.display.set_caption("Right Hand Skeleton Viewer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 16)

        # State
        self.latest_joints = None
        self.smoothed = None          # EMA buffer, shape (21, 3) after first frame
        self.latest_frame_id = 0
        self.latest_latency = 0.0
        self.last_packet_time = 0.0
        self.packet_count = 0
        self.running = True
        self.timeout_sec = 2.0

    # ------------------------------------------------------------------
    # Project 3D → 2D screen
    # ------------------------------------------------------------------
    def project(self, x, y, z):
        if self.axis == "xy":
            sx, sy = x, -y
        elif self.axis == "xz":
            sx, sy = x, -z
        else:  # yz
            sx, sy = y, -z
        if self.flip_x:
            sx = -sx
        if self.flip_y:
            sy = -sy
        px = int(sx * self.scale + self.width / 2)
        py = int(sy * self.scale + self.height / 2)
        return px, py

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def draw_hex(self, surf, cx, cy, radius, color, width=0):
        pts = []
        for i in range(6):
            a = math.pi / 3 * i - math.pi / 6
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        pygame.draw.polygon(surf, color, pts, width)

    def draw_bone_glow(self, surf, p1, p2):
        """Multi-pass line for a cheap glow effect."""
        pygame.draw.line(surf, BONE_GLOW_WIDE, p1, p2, 9)
        pygame.draw.line(surf, BONE_GLOW_MID, p1, p2, 5)
        pygame.draw.line(surf, BONE_CORE, p1, p2, 3)
        pygame.draw.line(surf, BONE_BRIGHT, p1, p2, 1)

    # ------------------------------------------------------------------
    # Main loop helpers
    # ------------------------------------------------------------------
    def recv_packets(self):
        """Drain all queued UDP packets; keep only the latest."""
        latest = None
        while True:
            try:
                data, _addr = self.sock.recvfrom(4096)
                result = unpack_right_hand_packet(data)
                if result is not None:
                    latest = result
            except (socket.timeout, BlockingIOError, OSError):
                break
        if latest is not None:
            joints, fid, ts, _ver, _mt = latest
            self.latest_joints = joints
            self.latest_frame_id = fid
            self.latest_latency = (time.time() - ts) * 1000.0
            self.last_packet_time = time.time()
            self.packet_count += 1

    def apply_smoothing(self, joints):
        if self.smoothed is None:
            self.smoothed = [[float(v) for v in row] for row in joints]
            return joints
        alpha = 1.0 - self.smooth
        for i in range(N_JOINTS):
            for j in range(3):
                self.smoothed[i][j] = (alpha * joints[i][j] +
                                       (1.0 - alpha) * self.smoothed[i][j])
        return self.smoothed

    def render_frame(self):
        self.screen.fill(BG_COLOR)

        # Background grid (skip in low-power)
        if not self.low_power:
            step = 50
            for x in range(0, self.width, step):
                pygame.draw.line(self.screen, GRID_COLOR, (x, 0), (x, self.height), 1)
            for y in range(0, self.height, step):
                pygame.draw.line(self.screen, GRID_COLOR, (0, y), (self.width, y), 1)

        # Check timeout
        if (self.latest_joints is None or
                time.time() - self.last_packet_time > self.timeout_sec):
            txt = self.font.render("Waiting for right hand UDP data...",
                                   True, WAIT_TEXT)
            r = txt.get_rect(center=(self.width // 2, self.height // 2))
            self.screen.blit(txt, r)
            pygame.display.flip()
            return

        # Project all joints
        joints = self.apply_smoothing(self.latest_joints)
        proj = [self.project(*j) for j in joints]

        # Glow surface (skip in low-power)
        if not self.low_power:
            glow_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

            # Palm fill
            palm_pts = [proj[i] for i in PALM_POLY]
            pygame.draw.polygon(glow_surf, PALM_FILL, palm_pts)
            pygame.draw.polygon(glow_surf, PALM_LINE, palm_pts, 1)

            # Bones with glow
            for a, b in HAND_BONES:
                self.draw_bone_glow(glow_surf, proj[a], proj[b])

            # Joints – rings for knuckles, hex for tips
            for i, (px, py) in enumerate(proj):
                if i in FINGERTIPS:
                    self.draw_hex(glow_surf, px, py, 5, JOINT_TIP)
                    self.draw_hex(glow_surf, px, py, 7, (*JOINT_TIP, 60), 1)
                else:
                    pygame.draw.circle(glow_surf, JOINT_RING, (px, py), 4, 1)

            self.screen.blit(glow_surf, (0, 0))
        else:
            # Low-power: plain lines, no alpha
            palm_pts = [proj[i] for i in PALM_POLY]
            pygame.draw.polygon(self.screen, (0, 80, 120), palm_pts, 1)
            for a, b in HAND_BONES:
                pygame.draw.line(self.screen, BONE_LOW_POWER, proj[a], proj[b], 2)
            for i, (px, py) in enumerate(proj):
                color = JOINT_TIP if i in FINGERTIPS else JOINT_RING
                radius = 5 if i in FINGERTIPS else 3
                pygame.draw.circle(self.screen, color, (px, py), radius, 1)

        # HUD – top-left
        lines = [
            f"frame_id: {self.latest_frame_id}",
            f"fps: {self.clock.get_fps():.0f}",
            f"latency: {self.latest_latency:.1f} ms",
            f"pkts/sec: {self.packet_count}",
        ]
        for i, text in enumerate(lines):
            surf = self.font.render(text, True, HUD_TEXT)
            self.screen.blit(surf, (10, 6 + i * 18))

        pygame.display.flip()

    def run(self):
        fps_update_ts = time.time()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False

            self.recv_packets()

            # Reset packet counter every second
            now = time.time()
            if now - fps_update_ts >= 1.0:
                self.packet_count = 0
                fps_update_ts = now

            self.render_frame()
            self.clock.tick(self.target_fps)

        self.sock.close()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Right-hand skeleton viewer (pygame + UDP)")
    parser.add_argument("--listen-ip", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--scale", type=float, default=220)
    parser.add_argument("--flip-x", action="store_true")
    parser.add_argument("--flip-y", action="store_true")
    parser.add_argument("--axis", choices=["xy", "xz", "yz"], default="xy")
    parser.add_argument("--smooth", type=float, default=0.0)
    parser.add_argument("--low-power", action="store_true")
    args = parser.parse_args()

    viewer = HandViewer(args)
    viewer.run()


if __name__ == "__main__":
    main()
