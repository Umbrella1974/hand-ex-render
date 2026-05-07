# Hand UDP Viewer

Lightweight right-hand skeleton UDP transport + pygame renderer for Windows.
Linux side sends 21-joint (MediaPipe order) float32 data; Windows side displays
a tech-style skeleton with no heavy 3D engine.

## Quick start (same machine test)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the receiver (Window 1)
python hand_viewer_pygame.py --port 5005

# 3. Start the dummy sender (Window 2)
python send_dummy_hand.py --target-ip 127.0.0.1 --port 5005 --rate 30
```

You should see a right-hand skeleton animating in the pygame window.

## Cross-machine test

```bash
# Windows receiver
python hand_viewer_pygame.py --port 5005

# Linux sender (replace 192.168.1.50 with your Windows IP)
python send_dummy_hand.py --target-ip 192.168.1.50 --port 5005 --rate 30
```

## CLI reference

### Receiver – `hand_viewer_pygame.py`

| Flag | Default | Description |
|---|---|---|
| `--listen-ip` | `0.0.0.0` | Bind address |
| `--port` | `5005` | UDP port |
| `--width` | `960` | Window width |
| `--height` | `720` | Window height |
| `--fps` | `30` | Render target FPS |
| `--scale` | `220` | Pixel scale for projected coordinates |
| `--flip-x` | off | Mirror horizontally |
| `--flip-y` | off | Mirror vertically |
| `--axis` | `xy` | Projection plane: `xy`, `xz`, or `yz` |
| `--smooth` | `0.0` | EMA smoothing factor (0.3~0.5 recommended if jittery) |
| `--low-power` | off | Disable glow & background grid |

### Sender – `send_dummy_hand.py`

| Flag | Default | Description |
|---|---|---|
| `--target-ip` | `127.0.0.1` | Receiver IP |
| `--port` | `5005` | Receiver port |
| `--rate` | `30` | Packets per second |

## Troubleshooting

### "Waiting for right hand UDP data..." stuck on screen

1. Check the Windows IP address – the sender must target the correct IP.
2. Verify both sides use the same port (default 5005).
3. Check Windows Firewall – allow Python UDP on the chosen port.
   - Go to *Windows Defender Firewall* → *Allow an app through firewall*.
   - Add `python.exe` or temporarily disable the firewall for testing.
4. Test locally first with `127.0.0.1` on a single machine.
5. Try `--low-power --fps 20 --width 640 --height 480` to reduce GPU load.

### Hand orientation is wrong

- Use `--axis xy` / `--axis xz` / `--axis yz` to switch the projection plane.
- Use `--flip-x` and/or `--flip-y` to mirror axes.
- Use `--scale` to resize (larger = bigger hand).

### Jitter / shaky hand

- Add `--smooth 0.3` or `--smooth 0.5` for EMA temporal smoothing.
- Higher values = smoother but more latency.

### Low frame rate

- Use `--low-power` to disable glow and background grid.
- Lower the target FPS: `--fps 20`.
- Reduce window size: `--width 640 --height 480`.

## Project structure

```
hand_udp_viewer/
├── README.md
├── requirements.txt
├── protocol.py              # shared pack / unpack
├── send_dummy_hand.py       # dummy data sender
├── hand_viewer_pygame.py    # Windows receiver + renderer
└── send_ros_hand_stub.py    # ROS bridge template
```

## Protocol

```
Offset  Size  Field
0       4     magic      b"VTLP"
4       1     version    uint8 (1)
5       1     msg_type   uint8 (11 = right hand)
6       4     frame_id   uint32
10      8     timestamp  float64 (seconds)
18      2     n_floats   uint16 (63)
20      252   payload    21×3 float32 LE
```

## Adding real ROS / VisionPro data

1. Edit `send_ros_hand_stub.py` – implement `convert_to_21x3()`.
2. Wire the ROS subscriber callback to call `pack_right_hand_packet()`.
3. Run the stub as a separate process on the Linux machine.
4. The Windows receiver stays unchanged — it only knows 21×3 float32.
