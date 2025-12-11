using System;
using System.Collections;
using System.Collections.Generic;
using System.Net.Sockets;
using UnityEngine;
using UnityEngine.XR;

public class ImuStreamer : MonoBehaviour
{
    [Header("Network Settings")]
    [Tooltip("IPv4 address of your laptop running server.py")]
    public string laptopIp = "172.24.43.233";
    public int port = 5000;

    [Header("Sampling")]
    [Tooltip("Seconds between samples (0.02 = 50 Hz, 0.05 = 20 Hz)")]
    public float sampleIntervalSeconds = 0.05f;

    // TCP
    private TcpClient _client;
    private NetworkStream _stream;
    private bool _connected = false;

    // Buffers
    private readonly byte[] _header = new byte[16];
    private readonly byte[] _imuPayload = new byte[9 * 4];
    private readonly byte[] _posePayload = new byte[7 * 4];

    // XR devices
    private InputDevice _headDevice;
    private bool _headDeviceValid = false;
    private List<InputDevice> _devices = new List<InputDevice>();

    // Cached head transform
    private Transform _head;

    void Start()
    {
        Application.runInBackground = true;

        // Get main camera for head pose
        if (Camera.main != null)
        {
            _head = Camera.main.transform;
            Debug.Log("[ImuStreamer] Using Camera.main as head pose source.");
        }
        else
        {
            Debug.LogWarning("[ImuStreamer] No Camera.main found!");
        }

        // Get XR head device for IMU data
        StartCoroutine(InitializeXRDevice());

        // Connect to server
        try
        {
            Debug.Log($"[ImuStreamer] Connecting to {laptopIp}:{port} ...");
            _client = new TcpClient();
            _client.Connect(laptopIp, port);
            _stream = _client.GetStream();
            _connected = true;
            Debug.Log("[ImuStreamer] Connected to server.");

            StartCoroutine(SendLoop());
        }
        catch (Exception e)
        {
            Debug.LogError($"[ImuStreamer] Failed to connect: {e}");
            _connected = false;
        }
    }

    private IEnumerator InitializeXRDevice()
    {
        // Wait a bit for XR to initialize
        yield return new WaitForSeconds(1f);

        // Try to get head device
        InputDevices.GetDevicesAtXRNode(XRNode.Head, _devices);

        if (_devices.Count > 0)
        {
            _headDevice = _devices[0];
            _headDeviceValid = _headDevice.isValid;
            Debug.Log($"[ImuStreamer] Found XR head device: {_headDevice.name}");
            Debug.Log($"[ImuStreamer] Device valid: {_headDeviceValid}");

            // List available features for debugging
            List<InputFeatureUsage> features = new List<InputFeatureUsage>();
            if (_headDevice.TryGetFeatureUsages(features))
            {
                Debug.Log($"[ImuStreamer] Available features ({features.Count}):");
                foreach (var feature in features)
                {
                    Debug.Log($"  - {feature.name} ({feature.type})");
                }
            }
        }
        else
        {
            Debug.LogWarning("[ImuStreamer] No XR head device found!");
        }

        // Keep checking for device changes
        InputDevices.deviceConnected += OnDeviceConnected;
    }

    private void OnDeviceConnected(InputDevice device)
    {
        Debug.Log($"[ImuStreamer] Device connected: {device.name}");
        if (device.characteristics.HasFlag(InputDeviceCharacteristics.HeadMounted))
        {
            _headDevice = device;
            _headDeviceValid = device.isValid;
        }
    }

    private IEnumerator SendLoop()
    {
        var wait = new WaitForSeconds(sampleIntervalSeconds);

        while (_connected)
        {
            try
            {
                SendImuSample();
                SendPoseSample();
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

        // Try to get IMU data from XR device
        Vector3 acc = Vector3.zero;
        Vector3 gyro = Vector3.zero;
        bool gotData = false;

        if (_headDeviceValid && _headDevice.isValid)
        {
            // Try to get acceleration
            if (_headDevice.TryGetFeatureValue(CommonUsages.deviceAcceleration, out acc))
            {
                // Convert from m/s^2 to g
                acc = acc / 9.81f;
                gotData = true;
            }

            // Try to get angular velocity
            if (_headDevice.TryGetFeatureValue(CommonUsages.deviceAngularVelocity, out gyro))
            {
                gotData = true;
            }
        }

        // If XR didn't work, try legacy Input as fallback
        if (!gotData)
        {
            if (SystemInfo.supportsAccelerometer)
            {
                acc = Input.acceleration;
            }
            if (SystemInfo.supportsGyroscope)
            {
                Input.gyro.enabled = true;
                gyro = Input.gyro.rotationRateUnbiased;
            }
        }

        float ax = acc.x, ay = acc.y, az = acc.z;
        float gx = gyro.x, gy = gyro.y, gz = gyro.z;
        float mx = 0f, my = 0f, mz = 0f; // No magnetometer

        // Log occasionally for debugging
        if (Time.frameCount % 100 == 0)
        {
            Debug.Log($"[ImuStreamer] acc=({ax:F3},{ay:F3},{az:F3}) gyro=({gx:F3},{gy:F3},{gz:F3})");
        }

        // Pack payload
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

        // Header
        byte type = 1;
        byte sensorId = 0;
        ushort reserved = 0;
        ulong tNs = (ulong)(Time.realtimeSinceStartupAsDouble * 1e9);

        _header[0] = type;
        _header[1] = sensorId;
        WriteUInt16BE(_header, 2, reserved);
        WriteUInt64BE(_header, 4, tNs);
        WriteUInt32BE(_header, 12, payloadLen);

        _stream.Write(_header, 0, _header.Length);
        _stream.Write(_imuPayload, 0, _imuPayload.Length);
        _stream.Flush();
    }

    private void SendPoseSample()
    {
        if (_head == null)
            return;

        if (_stream == null || !_stream.CanWrite)
            throw new InvalidOperationException("Stream is not writable.");

        // Get actual tracked position and rotation
        Vector3 pos = _head.position;
        Quaternion rot = _head.rotation;

        // Log occasionally for debugging
        if (Time.frameCount % 100 == 0)
        {
            Debug.Log($"[ImuStreamer] pos=({pos.x:F3},{pos.y:F3},{pos.z:F3}) rot=({rot.x:F3},{rot.y:F3},{rot.z:F3},{rot.w:F3})");
        }

        WriteFloatBE(_posePayload, 0, pos.x);
        WriteFloatBE(_posePayload, 4, pos.y);
        WriteFloatBE(_posePayload, 8, pos.z);
        WriteFloatBE(_posePayload, 12, rot.x);
        WriteFloatBE(_posePayload, 16, rot.y);
        WriteFloatBE(_posePayload, 20, rot.z);
        WriteFloatBE(_posePayload, 24, rot.w);

        uint payloadLen = (uint)_posePayload.Length;
        byte type = 2;
        byte sensorId = 0;
        ushort reserved = 0;
        ulong tNs = (ulong)(Time.realtimeSinceStartupAsDouble * 1e9);

        _header[0] = type;
        _header[1] = sensorId;
        WriteUInt16BE(_header, 2, reserved);
        WriteUInt64BE(_header, 4, tNs);
        WriteUInt32BE(_header, 12, payloadLen);

        _stream.Write(_header, 0, _header.Length);
        _stream.Write(_posePayload, 0, _posePayload.Length);
        _stream.Flush();
    }

    // Helper methods
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

    void OnDestroy()
    {
        InputDevices.deviceConnected -= OnDeviceConnected;

        try
        {
            _stream?.Close();
            _client?.Close();
        }
        catch { }
    }
}