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

    private TcpClient _client;
    private NetworkStream _stream;

    private readonly byte[] _header = new byte[16];     // 16-byte header
    private readonly byte[] _payload = new byte[9 * 4]; // 9 floats = 36 bytes

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
                SendOneSample();
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

    private void SendOneSample()
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
        WriteFloatBE(_payload, 0, ax);
        WriteFloatBE(_payload, 4, ay);
        WriteFloatBE(_payload, 8, az);
        WriteFloatBE(_payload, 12, gx);
        WriteFloatBE(_payload, 16, gy);
        WriteFloatBE(_payload, 20, gz);
        WriteFloatBE(_payload, 24, mx);
        WriteFloatBE(_payload, 28, my);
        WriteFloatBE(_payload, 32, mz);

        uint payloadLen = (uint)_payload.Length;

        // 3) Header: !BBHQI (big-endian)
        byte type = 1;        // IMU
        byte sensorId = 0;    // main IMU
        ushort reserved = 0;

        double tSeconds = Time.realtimeSinceStartupAsDouble;
        ulong tNs = (ulong)(tSeconds * 1e9);

        _header[0] = type;
        _header[1] = sensorId;
        WriteUInt16BE(_header, 2, reserved);
        WriteUInt64BE(_header, 4, tNs);
        WriteUInt32BE(_header, 12, payloadLen);

        // 4) Send
        _stream.Write(_header, 0, _header.Length);
        _stream.Write(_payload, 0, _payload.Length);
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
