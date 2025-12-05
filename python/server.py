import socket # For network communication (TCP servers)
import struct # For packing and unpacking binary data
from pathlib import Path # For file Paths

HOST = "" # 
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

def recv_all(conn: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data
def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Server listening on port {PORT}...")

    conn, addr = server.accept()
    print(f"Connection from {addr}")

    try:
        header_bytes = recv_all(conn, header_size)
        typ, sensor_id, reserved, t_ns, payload_len = struct.unpack(header_format, header_bytes)
        print(f"Received header: type={typ}, sensor_id={sensor_id}, t_ns={t_ns}, payload_len={payload_len}")
        payload = recv_all(conn, payload_len)
        print(f"Received payload of length {len(payload)} bytes")
    finally:
        conn.close()
        server.close()
        print("Connection closed.")

if __name__ == "__main__":
    main()