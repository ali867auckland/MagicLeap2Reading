using System;
using System.Collections;
using System.Net.Sockets;
using UnityEngine;
using UnityEngine.InputSystem;  // NEW: Input System sensors

public class ImuStreamer : MonoBehaviour
{
    [Header("Network Settings")]
    [Tooltip("IPv4 address of your laptop running server.py")]
    public string laptopIp = "172.24.43.233";  // set to your laptop's IP
    public int port = 5000;                   // must match PORT in server.py

    [Header("Sampling")]
    [Tooltip("Seconds between IMU samples (0.05 = 20 Hz)")]
    public float sampleIntervalSeconds = 0.05f;

    [Header("Header Pose")]
    [Tooltip("Head transform (usually main camera). if empty, Camera.main will be used")]
    public Transform headTransform;

    private TcpClient _client;
    private NetworkStream _stream;

    private readonly byte[] _imuHeader = new byte[16];     // 16-byte header
    private readonly byte[] _imuPayload = new byte[9 * 4]; // 9 floats = 36 bytes

    private readonly byte[] _poseHeader = new byte[16];
    private readonly byte[] _posePayload = new byte[7 * 4];

    private bool _connected = false;

    // NEW: references to Input System sensors
    private UnityEngine.InputSystem.Gyroscope _gyro;
    private UnityEngine.InputSystem.Accelerometer _accel;

    void Start()
    {
        Application.runInBackground = true; // keep running if display dims

        // ---- 1) Get and enable sensors via Input System ----
        _gyro = UnityEngine.InputSystem.Gyroscope.current;
        _accel = UnityEngine.InputSystem.Accelerometer.current;

        if (_gyro == null || _accel == null)
        {
            Debug.LogError("[ImuStreamer] Gyroscope or Accelerometer not available. " +
                           "Check Input System is installed and Active Input Handling is 'Both' or 'Input System'.");
        }
        else
        {
            InputSystem.EnableDevice(_gyro);
            InputSystem.EnableDevice(_accel);
            Debug.Log("[ImuStreamer] Enabled Gyroscope and Accelerometer.");
        }

        // ---- 2) Connect to laptop TCP server ----
        try
        {
            Debug.Log($"[ImuStreamer] Connecting to {laptopIp}:{port}...");
            _client = new TcpClient();
            _client.Connect(laptopIp, port);
            _stream = _client.GetStream();
            _connected = true;
            Debug.Log("[ImuStreamer] Connected!");
            StartCoroutine(SendLoop());
        }
        catch (Exception e)
        {
            Debug.LogError($"[ImuStreamer] Failed to connect: {e}");
            _connected = false;
        }
    }

    IEnumerator SendLoop()
    {
        var wait = new WaitForSeconds(sampleIntervalSeconds);

        while (_connected)
        {
            try
            {
                SendImuSample();
            }
            catch (Exception e)
            {
                Debug.LogError($"[ImuStreamer] Error while sending: {e}");
                _connected = false;
                break;
            }

            yield return wait;
        }

        Debug.Log("[ImuStreamer] SendLoop stopped.");
    }

    private void SendImuSample()
    {
        if (_stream == null || !_stream.CanWrite)
            throw new InvalidOperationException("Stream is not writable.");

        if (_gyro == null || _accel == null || !_gyro.enabled || !_accel.enabled)
        {
            // Sensors not ready; skip this frame
            return;
        }

        // 1) Read IMU from Input System sensors
        Vector3 acc = _accel.acceleration.ReadValue();   // m/s^2
        Vector3 gyro = _gyro.angularVelocity.ReadValue(); // rad/s

        float ax = acc.x, ay = acc.y, az = acc.z;
        float gx = gyro.x, gy = gyro.y, gz = gyro.z;

        // magnetometer still zero for now
        float mx = 0f, my = 0f, mz = 0f;

        // Optional: log to Unity console so you can see the values changing
        // Debug.Log($"[ImuStreamer] acc={acc}, gyro={gyro}");

        // 2) Pack payload: 9 floats big-endian
        WriteFloatBE(_imuPayload, 0, ax);
        WriteFloatBE(_imuPayload, 4, ay);
        WriteFloatBE(_imuPayload, 8, az);
        WriteFloatBE(_imuPayload, 12, gx);
        WriteFloatBE(_imuPayload, 16, gy);
        WriteFloatBE(_imuPayload, 20, gz);
        WriteFloatBE(_imuPayload, 24, mx);
        WriteFloatBE(_imuPayload, 28, my);
        WriteFloatBE(_imuPayload, 32, mz);

        uint payloadLen = (uint)_imuPayload.Length;

        // 3) Header: !BBHQI (big-endian)
        byte type = 1;        // IMU
        byte sensorId = 0;    // main IMU
        ushort reserved = 0;

        double tSeconds = Time.realtimeSinceStartupAsDouble;
        ulong tNs = (ulong)(tSeconds * 1e9);

        _imuHeader[0] = type;
        _imuHeader[1] = sensorId;
        WriteUInt16BE(_imuHeader, 2, reserved);
        WriteUInt64BE(_imuHeader, 4, tNs);
        WriteUInt32BE(_imuHeader, 12, payloadLen);

        // 4) Send
        _stream.Write(_imuHeader, 0, _imuHeader.Length);
        _stream.Write(_imuPayload, 0, _imuPayload.Length);
        _stream.Flush();
    }

    // ---- helpers ----
    private static void WriteUInt16BE(byte[] buffer, int offset, ushort value)
    {
        buffer[offset] = (byte)(value >> 8);
        buffer[offset + 1] = (byte)value;
    }

    private static void WriteUInt32BE(byte[] buffer, int offset, uint value)
    {
        buffer[offset] = (byte)(value >> 24);
        buffer[offset + 1] = (byte)(value >> 16);
        buffer[offset + 2] = (byte)(value >> 8);
        buffer[offset + 3] = (byte)value;
    }

    private static void WriteUInt64BE(byte[] buffer, int offset, ulong value)
    {
        buffer[offset] = (byte)(value >> 56);
        buffer[offset + 1] = (byte)(value >> 48);
        buffer[offset + 2] = (byte)(value >> 40);
        buffer[offset + 3] = (byte)(value >> 32);
        buffer[offset + 4] = (byte)(value >> 24);
        buffer[offset + 5] = (byte)(value >> 16);
        buffer[offset + 6] = (byte)(value >> 8);
        buffer[offset + 7] = (byte)value;
    }

    private static void WriteFloatBE(byte[] buffer, int offset, float value)
    {
        byte[] tmp = BitConverter.GetBytes(value);
        if (BitConverter.IsLittleEndian) Array.Reverse(tmp);
        Buffer.BlockCopy(tmp, 0, buffer, offset, 4);
    }

    void OnApplicationQuit()
    {
        try { _stream?.Close(); _client?.Close(); }
        catch { }
    }
}
