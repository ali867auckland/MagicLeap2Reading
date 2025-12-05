#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <math.h>

#define SERVER_IP   "127.0.0.1"
#define SERVER_PORT 50000

static uint64_t htonll(uint64_t x) {
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    return ((uint64_t)htonl((uint32_t)(x & 0xFFFFFFFFULL)) << 32) |
           htonl((uint32_t)(x >> 32));
#else
    return x;
#endif
}

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

int main(void) {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) {
        perror("socket");
        return 1;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(SERVER_PORT);
    if (inet_pton(AF_INET, SERVER_IP, &addr.sin_addr) <= 0) {
        perror("inet_pton");
        close(sock);
        return 1;
    }

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("connect");
        close(sock);
        return 1;
    }
    printf("Connected to %s:%d\n", SERVER_IP, SERVER_PORT);

    float ax = sinf(0.0f);
    float ay = cosf(0.0f);
    float az = 1.0f;
    float gx = 0.1f;
    float gy = 0.2f;
    float gz = 0.3f;
    float mx = 0.0f;
    float my = 0.0f;
    float mz = 0.0f;

    float vals[9] = { ax, ay, az, gx, gy, gz, mx, my, mz };

    uint8_t imu_payload[9 * 4];
    for (int i = 0; i < 9; ++i) {
        uint32_t bits;
        memcpy(&bits, &vals[i], sizeof(float));
        bits = htonl(bits);
        memcpy(&imu_payload[i * 4], &bits, sizeof(uint32_t));
    }
    uint32_t payload_len = sizeof(imu_payload);

    uint8_t header[16];

    uint8_t  type      = 1;
    uint8_t  sensor_id = 0;
    uint16_t reserved  = 0;
    uint64_t t_ns      = now_ns();

    header[0] = type;
    header[1] = sensor_id;

    uint16_t reserved_be = htons(reserved);
    memcpy(&header[2], &reserved_be, sizeof(uint16_t));

    uint64_t t_ns_be = htonll(t_ns);
    memcpy(&header[4], &t_ns_be, sizeof(uint64_t));

    uint32_t payload_len_be = htonl(payload_len);
    memcpy(&header[12], &payload_len_be, sizeof(uint32_t));

    ssize_t sent = send(sock, header, sizeof(header), 0);
    if (sent != (ssize_t)sizeof(header)) {
        perror("send header");
        close(sock);
        return 1;
    }

    sent = send(sock, imu_payload, payload_len, 0);
    if (sent != (ssize_t)payload_len) {
        perror("send payload");
        close(sock);
        return 1;
    }

    printf("Sent one IMU packet.\n");

    close(sock);
    return 0;
}
