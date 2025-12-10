import socket # For network communication (TCP servers)
import struct # For packing and unpacking binary data
from pathlib import Path
from turtle import write # For file Paths

HOST = "0.0.0.0" 
PORT = 5000
 
###
# Header format:
# "!": Network byte order (big-endian)
# "B": 1 byte: Type of sensor data (uint8) (unsigned char)
# "B": 1 byte: sensor_id, which sensor (left,centre,right) (uint8) (unsigned char)
# "H": 2 bytes: reserved (uint16) (unsigned short)
# "Q": 8 bytes: t_ns, timestamp (uint64) (unsigned long long)
# "I": 4 bytes: payload_len, length of data (uint32) (unsigned int)
###
header_format = "!BBHQI" 
header_size = struct.calcsize(header_format) # Calculate size of header

IMU_Format = "!9f" # 9 floats for IMU data
IMU_Size = struct.calcsize(IMU_Format) # Calculate size of IMU data

def recv_all(conn: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data

def main():
    directory = Path("ML2_readings")
    directory.mkdir(exist_ok=True)

    imu_file = open(directory / "imu.csv", "w", buffering = 1)
    imu_file.write("t_ns,accx,accy,accz,gyrox,gyroy,gyroz,magx,magy,magz\n") # CSV Header

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Server listening on port {PORT}...")

    conn, addr = server.accept()
    print(f"Connection from {addr}")

    try:
        while True:
            try:
                header_bytes = recv_all(conn, header_size)
            except ConnectionError:
                print("Connection closed by client.")
                break
            typ, sensor_id, reserved, t_ns, payload_len = struct.unpack(header_format, header_bytes)
            print(f"Received header: type={typ}, sensor_id={sensor_id}, t_ns={t_ns}, payload_len={payload_len}")
        
            try:
                payload = recv_all(conn, payload_len)
            except ConnectionError:
                print("Connection closed by client.")
                break

            if typ == 1: # IMU data
                if payload_len != IMU_Size:
                    print(f"Unexpected IMU payload size: {payload_len}")
                    continue

                accx, accy, accz, gyrox, gyroy, gyroz, magx, magy, magz = struct.unpack(IMU_Format, payload)
                imu_file.write(f"{t_ns},{accx},{accy},{accz},{gyrox},{gyroy},{gyroz},{magx},{magy},{magz}\n")
                
                print(
                    f"IMU Data - t_ns: {t_ns}, "
                    f"Acc: ({accx}, {accy}, {accz}), "
                    f"Gyro: ({gyrox}, {gyroy}, {gyroz}), "
                    f"Mag: ({magx}, {magy}, {magz})"
                )
            else:
                print(f"Unknown data type: {typ}")
    finally:
        conn.close()
        server.close()
        print("Connection closed.")

if __name__ == "__main__":
    main()