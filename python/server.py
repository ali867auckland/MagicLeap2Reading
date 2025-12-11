import socket
import struct
import csv
import os
from datetime import datetime, timezone


HOST = "0.0.0.0"   # listen on all interfaces
PORT = 5000        # must match port in ImuStreamer.cs

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUT_DIR = os.path.join(SCRIPT_DIR, "ML2_readings")
OUT_FILE = os.path.join(OUT_DIR, "imu.csv")

# Header: !BBHQI  -> type (1), sensorId (1), reserved (2), t_ns (8), payload_len (4)
HEADER_SIZE = 16

# Payload: 9 floats big-endian -> ax, ay, az, gx, gy, gz, mx, my, mz
IMU_PAYLOAD_SIZE = 9 * 4  # 9 floats = 36 bytes


def read_exact(conn, n: int) -> bytes:
    """Read exactly n bytes from the socket or raise ConnectionError."""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        data += chunk
    return data


def open_csv():
    """Open imu.csv for append, create folder + header if needed."""
    os.makedirs(OUT_DIR, exist_ok=True)

    file_exists = os.path.exists(OUT_FILE)
    f = open(OUT_FILE, "a", newline="")
    writer = csv.writer(f)

    if not file_exists or os.path.getsize(OUT_FILE) == 0:
        # IMPORTANT: column names match your other scripts
        writer.writerow([
            "t_ns",
            "type",
            "sensorId",
            "accx", "accy", "accz",
            "gyrox", "gyroy", "gyroz",
            "magx", "magy", "magz",
            "server_time_iso",
        ])
        f.flush()

    return f, writer


def handle_client(conn: socket.socket, addr):
    print(f"[server] Connected from {addr}")
    f, writer = open_csv()

    try:
        while True:
            # ---- 1) Read and parse 16-byte header ----
            header = read_exact(conn, HEADER_SIZE)

            type_byte = header[0]
            sensor_id = header[1]
            # reserved = struct.unpack("!H", header[2:4])[0]  # not used, but available
            t_ns = struct.unpack("!Q", header[4:12])[0]
            payload_len = struct.unpack("!I", header[12:16])[0]

            if payload_len != IMU_PAYLOAD_SIZE:
                print(f"[server] Unexpected payload_len={payload_len}, skipping packet")
                # Still need to consume the payload bytes to keep stream in sync
                _ = read_exact(conn, payload_len)
                continue

            # ---- 2) Read IMU payload (9 floats, big-endian) ----
            payload = read_exact(conn, payload_len)
            ax, ay, az, gx, gy, gz, mx, my, mz = struct.unpack("!9f", payload)

            # ---- 3) Write one CSV row ----
            server_time_iso = datetime.now(timezone.utc).isoformat()

            # Order here matches the header row in open_csv()
            writer.writerow([
                t_ns,
                type_byte,
                sensor_id,
                ax, ay, az,         # -> accx, accy, accz
                gx, gy, gz,         # -> gyrox, gyroy, gyroz
                mx, my, mz,         # -> magx, magy, magz
                server_time_iso,
            ])
            f.flush()
    except ConnectionError as e:
        print(f"[server] Client disconnected: {e}")
    finally:
        f.close()
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
