"""Stub for converting ROS / VisionPro hand data to 21×3 and sending via UDP.

This file does NOT import any ROS packages.  It serves as a template for the
Linux-side bridge.  When real ROS data is available, fill in the marked
sections and run this as a standalone process.

Suggested integration:

1. Subscribe to your hand-tracking ROS topic (e.g. /right_hand/joints).
2. In the callback, call convert_to_21x3(msg) to get a (21,3) ndarray.
3. Call protocol.pack_right_hand_packet() and send via a UDP socket.

Keep the sending loop in a *separate process* so it never blocks the
teleoperation control loop.
"""

import socket
import argparse

# -- Uncomment when ROS is available --
# import numpy as np
# import rospy
# from your_hand_msgs.msg import HandJoints  # replace with actual message type

from protocol import pack_right_hand_packet


def convert_to_21x3(msg):
    """Convert a ROS/VisionPro hand message into a (21, 3) float32 ndarray.

    Args:
        msg: the ROS message object (type depends on your setup).

    Returns:
        np.ndarray of shape (21, 3), dtype float32.

    MediaPipe point order (0=wrist, 1-4=thumb, 5-8=index, 9-12=middle,
    13-16=ring, 17-20=pinky).
    """
    # ------------------------------------------------------------------
    # TODO: implement the conversion from *your* ROS message layout.
    # Example skeleton:
    #
    #   joints = np.zeros((21, 3), dtype=np.float32)
    #   for i in range(21):
    #       joints[i, 0] = msg.landmarks[i].x  # or whichever field name
    #       joints[i, 1] = msg.landmarks[i].y
    #       joints[i, 2] = msg.landmarks[i].z
    #   return joints
    # ------------------------------------------------------------------
    raise NotImplementedError("convert_to_21x3 – fill in your ROS message mapping")


def main():
    parser = argparse.ArgumentParser(
        description="ROS hand-data → UDP bridge (stub)")
    parser.add_argument("--target-ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frame_id = 0

    print(f"ROS hand stub ready.  Will send to {args.target_ip}:{args.port}")
    print("Implement convert_to_21x3() and wire the ROS subscriber, then")
    print("call pack_right_hand_packet(joints, frame_id) inside your callback.")
    print("Press Ctrl+C to stop.")

    # ------------------------------------------------------------------
    # TODO: initialise ROS node and subscribe to your topic here.
    #   rospy.init_node("hand_udp_bridge", anonymous=True)
    #   rospy.Subscriber("/right_hand/joints", HandJoints, callback)
    #   rospy.spin()
    # ------------------------------------------------------------------

    try:
        while True:
            # Placeholder — a real implementation would push packets from
            # the ROS callback (or a thread-safe queue), not here.
            pass
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
