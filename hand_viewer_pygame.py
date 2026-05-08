"""Lightweight right-hand skeleton viewer using pygame + UDP.

Mouse:
  Left-drag  = orbit (rotate view)
  Scroll     = zoom
  R key      = reset view
  D key      = toggle dark mode

Usage:
    python hand_viewer_pygame.py --port 5005
    python hand_viewer_pygame.py --dark              # original dark theme
    python hand_viewer_pygame.py --low-power --fps 20
"""

import argparse
import math
import socket
import time

import pygame

from protocol import unpack_right_hand_packet, N_JOINTS

# ---------------------------------------------------------------------------
# Bone connectivity – MediaPipe hand
# ---------------------------------------------------------------------------
HAND_BONES = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17), (5, 17),
]

FINGERTIPS = {4, 8, 12, 16, 20}
PALM_POLY = [0, 5, 9, 13, 17]

# ---------------------------------------------------------------------------
# Light theme (default)
# ---------------------------------------------------------------------------
LIGHT = {
    "bg":          (248, 248, 252),
    "grid":        (218, 218, 228),
    "bone_out":    (100, 140, 210, 90),
    "bone_core":   (35, 85, 175, 240),
    "bone_low":    (40, 90, 180),
    "joint_fill":  (50, 115, 210),
    "joint_lit":   (180, 210, 255),
    "tip_fill":    (235, 75, 45),
    "tip_lit":     (255, 180, 150),
    "palm_fill":   (80, 140, 220, 28),
    "palm_line":   (80, 140, 220, 120),
    "palm_low":    (60, 100, 170),
    "hud":         (55, 55, 75),
    "wait":        (140, 145, 160),
    "axis_x":      (220, 50, 50),
    "axis_y":      (50, 190, 50),
    "axis_z":      (50, 120, 230),
}

# ---------------------------------------------------------------------------
# Dark theme (--dark)
# ---------------------------------------------------------------------------
DARK = {
    "bg":          (10, 10, 18),
    "grid":        (28, 28, 48),
    "bone_out":    (0, 140, 200, 45),
    "bone_core":   (0, 210, 255, 230),
    "bone_low":    (0, 190, 240),
    "joint_fill":  (0, 200, 250),
    "joint_lit":   (160, 240, 255),
    "tip_fill":    (255, 160, 40),
    "tip_lit":     (255, 220, 150),
    "palm_fill":   (0, 160, 220, 35),
    "palm_line":   (0, 180, 240, 80),
    "palm_low":    (0, 120, 180),
    "hud":         (180, 200, 220),
    "wait":        (120, 130, 150),
    "axis_x":      (255, 80, 80),
    "axis_y":      (80, 255, 80),
    "axis_z":      (80, 160, 255),
}


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
        self.dark = args.dark
        self.pal = DARK if self.dark else LIGHT

        # Socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.listen_ip, self.port))
        self.sock.settimeout(0.001)

        # Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height),
                                              pygame.DOUBLEBUF)
        pygame.display.set_caption("Right Hand Skeleton Viewer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 16)
        self.font_small = pygame.font.Font(None, 13)

        # Orbit camera
        self.yaw = 0.0
        self.pitch = 0.0
        self.zoom = 1.0
        self.dragging = False
        self.last_mouse = (0, 0)
        self.orbit_sensitivity = 0.005

        # State
        self.latest_joints = None
        self.smoothed = None
        self.latest_frame_id = 0
        self.latest_latency = 0.0
        self.last_packet_time = 0.0
        self.packet_count = 0
        self.running = True
        self.timeout_sec = 2.0

    # ------------------------------------------------------------------
    # Rotation + projection
    # ------------------------------------------------------------------
    def rotate_point(self, x, y, z):
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        rx = cy * x + sy * z
        rz = -sy * x + cy * z
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        ry = cp * y - sp * rz
        rz2 = sp * y + cp * rz
        return rx, ry, rz2

    def project(self, x, y, z):
        rx, ry, rz = self.rotate_point(x, y, z)
        return self._project_rotated(rx, ry, rz)

    def _project_rotated(self, rx, ry, rz):
        """Screen coords from an already-rotated point."""
        if self.axis == "xy":
            sx, sy = rx, -ry
        elif self.axis == "xz":
            sx, sy = rx, -rz
        else:
            sx, sy = ry, -rz
        if self.flip_x:
            sx = -sx
        if self.flip_y:
            sy = -sy
        s = self.scale * self.zoom
        return int(sx * s + self.width / 2), int(sy * s + self.height / 2)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def draw_sphere_joint(self, surf, px, py, radius, fill, highlight):
        """Filled circle + offset highlight = cheap 3D sphere illusion."""
        pygame.draw.circle(surf, fill, (px, py), radius, 0)
        r2 = max(radius // 2, 2)
        off = max(radius // 4, 1)
        pygame.draw.circle(surf, highlight, (px - off, py - off), r2, 0)

    def draw_bone_stroke(self, surf, p1, p2,
                         outer_color, outer_w,
                         core_color, core_w):
        """Two-pass line: wide semi-transparent outline + solid core."""
        pygame.draw.line(surf, outer_color, p1, p2, outer_w)
        pygame.draw.line(surf, core_color, p1, p2, core_w)

    def draw_ground_grid(self):
        half_cells = 16
        cell_size = 0.06
        for i in range(-half_cells, half_cells + 1):
            off = i * cell_size
            p1 = self.project(off, -0.2, -half_cells * cell_size)
            p2 = self.project(off, -0.2, half_cells * cell_size)
            pygame.draw.line(self.screen, self.pal["grid"], p1, p2, 1)
            p1 = self.project(-half_cells * cell_size, -0.2, off)
            p2 = self.project(half_cells * cell_size, -0.2, off)
            pygame.draw.line(self.screen, self.pal["grid"], p1, p2, 1)

    def draw_axis_widget(self):
        """Orientation gizmo fixed to bottom-right corner, rotates with view."""
        cx = self.width - 70
        cy = self.height - 70
        size = 45

        # Rotated axis directions
        axes = [
            (self.rotate_point(1, 0, 0), self.pal["axis_x"]),
            (self.rotate_point(0, 1, 0), self.pal["axis_y"]),
            (self.rotate_point(0, 0, 1), self.pal["axis_z"]),
        ]

        # Widget background
        widget_rect = pygame.Rect(cx - 48, cy - 48, 96, 96)
        pygame.draw.rect(self.screen, self.pal["bg"], widget_rect)
        pygame.draw.rect(self.screen, self.pal["grid"], widget_rect, 1)

        for (rx, ry, rz), color in axes:
            sx, sy = rx, -ry   # xy projection for widget
            ex = int(cx + sx * size)
            ey = int(cy + sy * size)
            pygame.draw.line(self.screen, color, (cx, cy), (ex, ey), 3)

        pygame.draw.circle(self.screen, self.pal["hud"], (cx, cy), 4)

        # Labels
        for (rx, ry, rz), label in [(axes[0][0], "X"), (axes[1][0], "Y"), (axes[2][0], "Z")]:
            sx, sy = rx, -ry
            lx = int(cx + sx * (size + 12))
            ly = int(cy + sy * (size + 12))
            t = self.font_small.render(label, True, self.pal["hud"])
            self.screen.blit(t, (lx - 4, ly - 6))

    # ------------------------------------------------------------------
    # Main-loop helpers
    # ------------------------------------------------------------------
    def recv_packets(self):
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

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.yaw = 0.0
                    self.pitch = 0.0
                    self.zoom = 1.0
                elif event.key == pygame.K_d:
                    self.dark = not self.dark
                    self.pal = DARK if self.dark else LIGHT
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.dragging = True
                    self.last_mouse = event.pos
                elif event.button == 4:
                    self.zoom = min(10.0, self.zoom * 1.1)
                elif event.button == 5:
                    self.zoom = max(0.1, self.zoom / 1.1)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if self.dragging:
                    dx = event.pos[0] - self.last_mouse[0]
                    dy = event.pos[1] - self.last_mouse[1]
                    self.yaw -= dx * self.orbit_sensitivity
                    self.pitch += dy * self.orbit_sensitivity
                    self.pitch = max(-math.pi / 2, min(math.pi / 2, self.pitch))
                    self.last_mouse = event.pos
            elif event.type == pygame.MOUSEWHEEL:
                self.zoom *= 1.1 ** event.y
                self.zoom = max(0.1, min(10.0, self.zoom))

    def render_frame(self):
        pal = self.pal
        self.screen.fill(pal["bg"])

        if not self.low_power:
            self.draw_ground_grid()
        self.draw_axis_widget()

        # Timeout
        if (self.latest_joints is None or
                time.time() - self.last_packet_time > self.timeout_sec):
            txt = self.font.render("Waiting for right hand UDP data...",
                                   True, pal["wait"])
            r = txt.get_rect(center=(self.width // 2, self.height // 2))
            self.screen.blit(txt, r)
            pygame.display.flip()
            return

        joints = self.apply_smoothing(self.latest_joints)
        # Pre-rotate all joints, compute depth (= rotated Z)
        rotated = [self.rotate_point(*j) for j in joints]
        proj = [self._project_rotated(rx, ry, rz) for rx, ry, rz in rotated]
        depths = [rz for _, _, rz in rotated]

        # Unified draw list sorted far→near
        # Each entry: (depth, type, data)
        draw_list = []

        # Palm polygon
        palm_avg_depth = sum(depths[i] for i in PALM_POLY) / len(PALM_POLY)
        draw_list.append((palm_avg_depth, "palm", None))

        # Bones
        for a, b in HAND_BONES:
            d = (depths[a] + depths[b]) * 0.5
            draw_list.append((d, "bone", (a, b)))

        # Joints
        for i in range(N_JOINTS):
            draw_list.append((depths[i], "joint", i))

        draw_list.sort(key=lambda x: x[0])  # far → near

        if not self.low_power:
            glow = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

            for _, kind, data in draw_list:
                if kind == "palm":
                    palm_pts = [proj[i] for i in PALM_POLY]
                    pygame.draw.polygon(glow, pal["palm_fill"], palm_pts)
                    pygame.draw.polygon(glow, pal["palm_line"], palm_pts, 1)
                elif kind == "bone":
                    a, b = data
                    self.draw_bone_stroke(glow, proj[a], proj[b],
                                          pal["bone_out"], 13,
                                          pal["bone_core"], 6)
                else:  # joint
                    i = data
                    px, py = proj[i]
                    if i in FINGERTIPS:
                        self.draw_sphere_joint(glow, px, py, 8,
                                               pal["tip_fill"], pal["tip_lit"])
                    else:
                        self.draw_sphere_joint(glow, px, py, 6,
                                               pal["joint_fill"], pal["joint_lit"])

            self.screen.blit(glow, (0, 0))
        else:
            # Low-power: direct draw, still depth-sorted
            for _, kind, data in draw_list:
                if kind == "palm":
                    palm_pts = [proj[i] for i in PALM_POLY]
                    pygame.draw.polygon(self.screen, pal["palm_low"], palm_pts, 1)
                elif kind == "bone":
                    a, b = data
                    pygame.draw.line(self.screen, pal["bone_low"],
                                     proj[a], proj[b], 5)
                else:  # joint
                    i = data
                    px, py = proj[i]
                    color = pal["tip_fill"] if i in FINGERTIPS else pal["joint_fill"]
                    r = 8 if i in FINGERTIPS else 6
                    pygame.draw.circle(self.screen, color, (px, py), r, 0)

        # HUD
        lines = [
            f"frame_id: {self.latest_frame_id}",
            f"fps: {self.clock.get_fps():.0f}  latency: {self.latest_latency:.1f} ms",
            f"yaw: {math.degrees(self.yaw):.0f}  pitch: {math.degrees(self.pitch):.0f}  zoom: {self.zoom:.1f}",
        ]
        for i, text in enumerate(lines):
            surf = self.font.render(text, True, pal["hud"])
            self.screen.blit(surf, (10, 6 + i * 18))

        pygame.display.flip()

    def run(self):
        fps_update_ts = time.time()
        while self.running:
            self.handle_events()
            self.recv_packets()
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
    parser.add_argument("--scale", type=float, default=300)
    parser.add_argument("--flip-x", action="store_true")
    parser.add_argument("--flip-y", action="store_true")
    parser.add_argument("--axis", choices=["xy", "xz", "yz"], default="xy")
    parser.add_argument("--smooth", type=float, default=0.0)
    parser.add_argument("--low-power", action="store_true")
    parser.add_argument("--dark", action="store_true",
                        help="Use original dark theme")
    args = parser.parse_args()
    viewer = HandViewer(args)
    viewer.run()


if __name__ == "__main__":
    main()
