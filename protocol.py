"""UDP protocol for right-hand 21×3 float32 skeleton transmission.

Packet layout:
  magic:    4s   b"VTLP"
  version:  B    uint8
  msg_type: B    uint8  (MSG_HAND_RIGHT = 11)
  frame_id: I    uint32
  timestamp:d    float64
  n_floats: H    uint16 (always 63)
  payload:  63f   21×3 float32 joints
"""

import struct
import time

MAGIC = b"VTLP"
HEADER_FMT = "<4s B B I d H"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

MSG_HAND_RIGHT = 11

N_JOINTS = 21
N_DIMS = 3
N_FLOATS = N_JOINTS * N_DIMS  # 63
PAYLOAD_FMT = f"<{N_FLOATS}f"
PAYLOAD_SIZE = N_FLOATS * 4
PACKET_SIZE = HEADER_SIZE + PAYLOAD_SIZE


def pack_right_hand_packet(joints, frame_id, timestamp=None):
    """Pack 21×3 joints into a UDP-ready bytes packet.

    Args:
        joints: list-of-lists or 2D array, shape (21, 3).
        frame_id: uint32 monotonic frame counter.
        timestamp: float64 seconds; auto-generated when None.

    Returns:
        bytes of length PACKET_SIZE.
    """
    if timestamp is None:
        timestamp = time.time()
    flat = []
    for row in joints:
        flat.extend(float(v) for v in row)
    header = struct.pack(HEADER_FMT, MAGIC, 1, MSG_HAND_RIGHT,
                         frame_id, timestamp, N_FLOATS)
    payload = struct.pack(PAYLOAD_FMT, *flat)
    return header + payload


def unpack_right_hand_packet(data):
    """Unpack a UDP datagram into (joints, frame_id, timestamp, version, msg_type).

    Returns None when magic / msg_type / n_floats don't match or data is too short.
    """
    if len(data) < HEADER_SIZE + PAYLOAD_SIZE:
        return None
    header = data[:HEADER_SIZE]
    magic, version, msg_type, frame_id, timestamp, n_floats = \
        struct.unpack(HEADER_FMT, header)
    if magic != MAGIC or msg_type != MSG_HAND_RIGHT or n_floats != N_FLOATS:
        return None
    flat = struct.unpack(PAYLOAD_FMT, data[HEADER_SIZE:HEADER_SIZE + PAYLOAD_SIZE])
    joints = [[flat[i * 3 + j] for j in range(3)] for i in range(N_JOINTS)]
    return joints, frame_id, timestamp, version, msg_type
