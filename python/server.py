import socket
import struct
import csv
import os
from datetime import datetime, timezone

HOST = "0.0.0.0"
PORT = 5000

# Always save next to this script in python/ML2_readings
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "ML2_readings")

HEADER_SIZE = 16  # !BBHQI

# Payload sizes (bytes)
IMU_PAYLOAD_SIZE = 9 * 4        # 9 floats
HEADPOSE_PAYLOAD_SIZE = 7 * 4   # 7 floats

TYPE_IMU = 1
TYPE_HEADPOSE = 2


def read_exact(conn, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        data += chunk
    return data


def open_imu_csv():
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "imu.csv")
    file_exists = os.path.exists(path)

    f = open(path, "a", newline="")
    w = csv.writer(f)

    if not file_exists or os.path.getsize(path) == 0:
        # IMPORTANT: this matches the imu.csv you just showed
        w.writerow([
            "t_ns",
            "type",
            "sensorId",
            "accx", "accy", "accz",
            "gyrox", "gyroy", "gyroz",
            "magx", "magy", "magz",
            "server_time_iso",
        ])
        f.flush()

    return f, w


def open_headpose_csv():
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "headpose.csv")
    file_exists = os.path.exists(path)

    f = open(path, "a", newline="")
    w = csv.writer(f)

    if not file_exists or os.path.getsize(path) == 0:
        w.writerow([
            "t_ns",
            "type",
            "sensorId",
            "px", "py", "pz",
            "qx", "qy", "qz", "qw",
            "server_time_iso",
        ])
        f.flush()

    return f, w


def handle_client(conn: socket.socket, addr):
    print(f"[server] Connected from {addr}")

    imu_f, imu_w = open_imu_csv()
    pose_f, pose_w = open_headpose_csv()

    try:
        while True:
            # ---- 1) Header ----
            header = read_exact(conn, HEADER_SIZE)

            type_byte = header[0]
            sensor_id = header[1]
            t_ns = struct.unpack("!Q", header[4:12])[0]
            payload_len = struct.unpack("!I", header[12:16])[0]

            # ---- 2) Dispatch by type ----

            if type_byte == TYPE_IMU:
                if payload_len != IMU_PAYLOAD_SIZE:
                    print(f"[server] Unexpected IMU payload_len={payload_len}, skipping")
                    _ = read_exact(conn, payload_len)
                    continue

                payload = read_exact(conn, payload_len)
                ax, ay, az, gx, gy, gz, mx, my, mz = struct.unpack("!9f", payload)

                server_time_iso = datetime.now(timezone.utc).isoformat()

                imu_w.writerow([
                    t_ns,
                    type_byte,
                    sensor_id,
                    ax, ay, az,
                    gx, gy, gz,
                    mx, my, mz,
                    server_time_iso,
                ])
                imu_f.flush()

            elif type_byte == TYPE_HEADPOSE:
                if payload_len != HEADPOSE_PAYLOAD_SIZE:
                    print(f"[server] Unexpected HEADPOSE payload_len={payload_len}, skipping")
                    _ = read_exact(conn, payload_len)
                    continue

                payload = read_exact(conn, payload_len)
                px, py, pz, qx, qy, qz, qw = struct.unpack("!7f", payload)

                server_time_iso = datetime.now(timezone.utc).isoformat()

                pose_w.writerow([
                    t_ns,
                    type_byte,
                    sensor_id,
                    px, py, pz,
                    qx, qy, qz, qw,
                    server_time_iso,
                ])
                pose_f.flush()

            else:
                # Unknown sensor type -> just consume and ignore
                print(f"[server] Skipping packet with unknown type={type_byte}")
                _ = read_exact(conn, payload_len)

    except ConnectionError as e:
        print(f"[server] Client disconnected: {e}")
    finally:
        imu_f.close()
        pose_f.close()
        conn.close()
        print("[server] Connection closed")


def main():
    print(f"[server] Listening on {HOST}:{PORT} ...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(1)

        while True:
            conn, addr = s.accept()
            handle_client(conn, addr)


if __name__ == "__main__":
    main()
