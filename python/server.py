import socket
import struct
import csv

HOST = "0.0.0.0"   # listen on all interfaces so the headset can connect
PORT = 5000

HEADER_FMT = "!BBHQI"      # type, sensor_id, reserved, t_ns, payload_len
HEADER_SIZE = struct.calcsize(HEADER_FMT)

IMU_FMT = "!9f"            # ax, ay, az, gx, gy, gz, mx, my, mz
IMU_SIZE = struct.calcsize(IMU_FMT)

POSE_FMT = "!7f"           # px, py, pz, qx, qy, qz, qw
POSE_SIZE = struct.calcsize(POSE_FMT)


def recv_all(conn, n):
    """Receive exactly n bytes from conn, or None if the connection closes."""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def main():
    print(f"Listening on {HOST}:{PORT} ...")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)

    conn, addr = server.accept()
    print(f"Connection from {addr}")

    imu_file = open("imu.csv", "w", newline="")
    pose_file = open("pose.csv", "w", newline="")

    imu_writer = csv.writer(imu_file)
    pose_writer = csv.writer(pose_file)

    imu_writer.writerow(
        ["t_ns", "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z",
         "mag_x", "mag_y", "mag_z"]
    )
    pose_writer.writerow(
        ["t_ns", "pos_x", "pos_y", "pos_z", "quat_x", "quat_y", "quat_z", "quat_w"]
    )

    try:
        while True:
            header_bytes = recv_all(conn, HEADER_SIZE)
            if header_bytes is None:
                print("Connection closed by client.")
                break

            typ, sensor_id, reserved, t_ns, payload_len = struct.unpack(
                HEADER_FMT, header_bytes
            )

            payload = recv_all(conn, payload_len)
            if payload is None:
                print("Connection closed while reading payload.")
                break

            if typ == 1 and payload_len == IMU_SIZE:
                ax, ay, az, gx, gy, gz, mx, my, mz = struct.unpack(IMU_FMT, payload)
                imu_writer.writerow([t_ns, ax, ay, az, gx, gy, gz, mx, my, mz])
                imu_file.flush()
                print(f"IMU  t={t_ns}  acc=({ax:.3f},{ay:.3f},{az:.3f})  "
                      f"gyro=({gx:.3f},{gy:.3f},{gz:.3f})")

            elif typ == 2 and payload_len == POSE_SIZE:
                px, py, pz, qx, qy, qz, qw = struct.unpack(POSE_FMT, payload)
                pose_writer.writerow([t_ns, px, py, pz, qx, qy, qz, qw])
                pose_file.flush()
                print(f"POSE t={t_ns}  pos=({px:.3f},{py:.3f},{pz:.3f})  "
                      f"quat=({qx:.3f},{qy:.3f},{qz:.3f},{qw:.3f})")

            else:
                print(f"Unknown type {typ} or unexpected payload_len={payload_len}")
    finally:
        imu_file.close()
        pose_file.close()
        conn.close()
        server.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
