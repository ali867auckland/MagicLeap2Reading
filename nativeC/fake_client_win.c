#define _WINSOCK_DEPRECATED_NO_WARNINGS

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

// Link WinSock automatically
#pragma comment(lib, "Ws2_32.lib")

// ---------------------------------------------
// Configuration
// ---------------------------------------------
#define SERVER_IP   "127.0.0.1"  // change later if server runs on another machine
#define SERVER_PORT 5000         // must match Python server PORT
#define NUM_PACKETS 100          // how many IMU samples to send
#define SAMPLE_INTERVAL_MS 50    // time between samples (~20 Hz)

// ---------------------------------------------
// Helper: timestamp in nanoseconds (relative)
// ---------------------------------------------
static uint64_t now_ns(void) {
    ULONGLONG ms = GetTickCount64();   // ms since system start
    return (uint64_t)ms * 1000000ULL;  // convert ms -> ns
}

// ---------------------------------------------
// Main
// ---------------------------------------------
int main(void) {
    WSADATA wsa;
    int r;

    // 1) Initialise WinSock
    r = WSAStartup(MAKEWORD(2, 2), &wsa);
    if (r != 0) {
        printf("WSAStartup failed: %d\n", r);
        return 1;
    }

    // 2) Create a TCP socket
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) {
        printf("socket failed: %ld\n", WSAGetLastError());
        WSACleanup();
        return 1;
    }

    // 3) Set up server address (IP + port) and connect
    {
        struct sockaddr_in addr;
        memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port   = htons(SERVER_PORT);

        addr.sin_addr.s_addr = inet_addr(SERVER_IP);
        if (addr.sin_addr.s_addr == INADDR_NONE) {
            printf("Invalid SERVER_IP: %s\n", SERVER_IP);
            closesocket(sock);
            WSACleanup();
            return 1;
        }

        if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
            printf("connect failed: %ld\n", WSAGetLastError());
            closesocket(sock);
            WSACleanup();
            return 1;
        }
    }

    printf("Connected to %s:%d\n", SERVER_IP, SERVER_PORT);

    // -----------------------------------------
    // 4) Streaming loop: send NUM_PACKETS IMU samples
    // -----------------------------------------
    {
        int sample_index;
        for (sample_index = 0; sample_index < NUM_PACKETS; ++sample_index) {
            // ---- 4.1 Generate fake IMU values for this sample ----
            float t = (float)sample_index * 0.1f;  // "time" param for the fake waveform

            // Simple fake patterns:
            float ax = sinf(t);
            float ay = cosf(t);
            float az = 1.0f;            // pretend gravity

            float gx = 0.01f * sample_index;
            float gy = 0.02f * sample_index;
            float gz = 0.03f * sample_index;

            float mx = 0.0f;
            float my = 0.0f;
            float mz = 0.0f;

            float vals[9] = { ax, ay, az, gx, gy, gz, mx, my, mz };

            // ---- 4.2 Pack floats into big-endian payload (9 * 4 = 36 bytes) ----
            {
                uint8_t imu_payload[9 * 4];
                uint32_t payload_len = (uint32_t)sizeof(imu_payload);
                int i;
                for (i = 0; i < 9; ++i) {
                    uint32_t bits;
                    memcpy(&bits, &vals[i], sizeof(float));   // copy float bits
                    bits = htonl(bits);                       // host -> network (big-endian)
                    memcpy(&imu_payload[i * 4], &bits, sizeof(uint32_t));
                }

                // ---- 4.3 Build 16-byte header for this packet ----
                {
                    uint8_t header[16];

                    uint8_t  type      = 1;   // 1 = IMU
                    uint8_t  sensor_id = 0;   // main IMU
                    uint16_t reserved  = 0;
                    uint64_t t_ns      = now_ns();

                    uint16_t reserved_be = htons(reserved);
                    uint64_t t_ns_be     = htonll(t_ns);
                    uint32_t payload_len_be = htonl(payload_len);

                    header[0] = type;
                    header[1] = sensor_id;
                    memcpy(&header[2],  &reserved_be,    sizeof(uint16_t));
                    memcpy(&header[4],  &t_ns_be,        sizeof(uint64_t));
                    memcpy(&header[12], &payload_len_be, sizeof(uint32_t));

                    // ---- 4.4 Send header then payload ----
                    {
                        int sent;

                        sent = send(sock, (const char*)header, (int)sizeof(header), 0);
                        if (sent != (int)sizeof(header)) {
                            printf("send header failed: %ld\n", WSAGetLastError());
                            closesocket(sock);
                            WSACleanup();
                            return 1;
                        }

                        sent = send(sock, (const char*)imu_payload, (int)payload_len, 0);
                        if (sent != (int)payload_len) {
                            printf("send payload failed: %ld\n", WSAGetLastError());
                            closesocket(sock);
                            WSACleanup();
                            return 1;
                        }

                        printf(
                            "Sent IMU sample %d: "
                            "acc=(%.3f, %.3f, %.3f) gyro=(%.3f, %.3f, %.3f)\n",
                            sample_index, ax, ay, az, gx, gy, gz
                        );
                    }
                }
            }

            // ---- 4.5 Wait before sending next sample ----
            Sleep(SAMPLE_INTERVAL_MS);  // milliseconds (Windows API)
        }
    }

    // 5) Clean up
    printf("Done streaming %d samples. Closing socket.\n", NUM_PACKETS);
    closesocket(sock);
    WSACleanup();
    return 0;
}
