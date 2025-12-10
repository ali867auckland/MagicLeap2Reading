using System;
using System.Collections;
using System.Net.Sockets;
using UnityEngine;

public class ImuStreamer : MonoBehaviour
{
    [Header("Network Settings")]
    [Tooltip("IPv4 address of your laptop running server.py")]
    public string laptopIp = "172.24.43.233";  // TODO: set to your laptop's IP
    public int port = 50000;                   // must match PORT in server.py

    [Header("Sampling")]
    [Tooltip("Seconds between samples (0.05 = 20 Hz)")]
    public float sampleIntervalSeconds = 0.05f;

    [Header("Head Pose")]
    [Tooltip("Assign the XR Camera / Head transform here")]
    public Transform headTransform;

    private TcpClient _client;
    private NetworkStream _stream;

    // Common 16-byte header buffer: !BBHQI  (type, sensor_id, reserved, t_ns, payload_len)
    private readonly byte[] _header = new byte[16];

    // IMU payload: 9 floats (acc, gyro, mag)
    private readonly byte[] _imuPayload = new byte[9 * 4];

    // Pose payload: 7 floats (pos XYZ, quat XYZW)
    private readonly byte[] _posePayload = new byte[7 * 4];

    private bool _connected = false;

    void Start()
    {
        Application.runInBackground = true; // keep running if display dims
        Input.gyro.enabled = true;         // enable Unity gyro

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
                // 1) Always send IMU
                SendImuSample();

                // 2) Also send head pose if we have a transform assigned
                if (headTransform != null)
                {
                    SendPoseSample();
                }
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

    // ---------------- IMU ----------------

    private void SendImuSample()
    {
        if (_stream == null || !_stream.CanWrite)
            throw new InvalidOperationException("Stream is not writable.");

        // 1) Read IMU from Unity
        Vector3 acc = Input.acceleration;                   // in g
        Vector3 gyro = Input.gyro.rotationRateUnbiased;     // rad/s

        float ax = acc.x, ay = acc.y, az = acc.z;
        float gx = gyro.x, gy = gyro.y, gz = gyro.z;

        // No magnetometer via Unity: send zeros for now
        float mx = 0f, my = 0f, mz = 0f;

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
        byte type = 1;        // 1 = IMU
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
        _stream.Write(_imuPayload, 0, _imuPayload.Length);
        _stream.Flush();
    }

    // ---------------- Head pose ----------------

    private void SendPoseSample()
    {
        if (_stream == null || !_stream.CanWrite)
            throw new InvalidOperationException("Stream is not writable.");

        if (headTransform == null)
        {
            // Nothing to send
            return;
        }

        // 1) Read pose from Unity (world-space)
        Vector3 pos = headTransform.position;      // meters
        Quaternion rot = headTransform.rotation;   // world rotation

        float px = pos.x, py = pos.y, pz = pos.z;
        // Unity quaternions are stored as (x, y, z, w)
        float qx = rot.x, qy = rot.y, qz = rot.z, qw = rot.w;

        // 2) Pack payload: 7 floats big-endian
        WriteFloatBE(_posePayload, 0, px);
        WriteFloatBE(_posePayload, 4, py);
        WriteFloatBE(_posePayload, 8, pz);
        WriteFloatBE(_posePayload, 12, qx);
        WriteFloatBE(_posePayload, 16, qy);
        WriteFloatBE(_posePayload, 20, qz);
        WriteFloatBE(_posePayload, 24, qw);

        uint payloadLen = (uint)_posePayload.Length;

        // 3) Header: !BBHQI (big-endian)
        byte type = 2;        // 2 = head pose
        byte sensorId = 0;    // main head
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
        _stream.Write(_posePayload, 0, _posePayload.Length);
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
        try
        {
            _stream?.Close();
            _client?.Close();
        }
        catch
        {
        }
    }
}
