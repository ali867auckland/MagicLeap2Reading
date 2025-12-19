package com.example.ml2nativerecorder

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.ImageFormat
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.camera2.*
import android.hardware.camera2.params.OutputConfiguration
import android.hardware.camera2.params.SessionConfiguration
import android.media.Image
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicBoolean

class Recorder(private val ctx: Context) {

    companion object {
        init { System.loadLibrary("native-lib") }
    }

    private external fun nativeInit(): Boolean
    private external fun nativeShutdown()

    private val running = AtomicBoolean(false)

    private lateinit var sessionDir: File
    private lateinit var camDir: File
    private lateinit var imuFile: File

    private var frameIndex = 0

    // Camera
    private lateinit var camThread: HandlerThread
    private lateinit var camHandler: Handler
    private lateinit var camExecutor: Executor
    private var camera: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null

    // IMU
    private lateinit var sensorManager: SensorManager
    private var imuOut: FileOutputStream? = null

    private val imuListener = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            if (!running.get()) return
            val monoNs = System.nanoTime()
            val line = buildString {
                append(monoNs).append(',')
                append(e.timestamp).append(',')
                append(e.sensor.type).append(',')
                append(e.values.joinToString(";"))
                append('\n')
            }
            imuOut?.write(line.toByteArray())
        }
        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
    }

    fun start(): File {
        if (running.getAndSet(true)) return sessionDir

        frameIndex = 0

        sessionDir = File(ctx.getExternalFilesDir(null), "sessions/${System.currentTimeMillis()}")
        camDir = File(sessionDir, "cam").apply { mkdirs() }
        imuFile = File(sessionDir, "imu.csv")
        sessionDir.mkdirs()

        val poseOk = nativeInit()
        if (!poseOk) Log.e("Recorder", "nativeInit failed (pose disabled). Continuing anyway.")

        // IMU logging
        sensorManager = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        imuOut = FileOutputStream(imuFile, true).also {
            it.write("mono_ns,sensor_ts_ns,type,values\n".toByteArray())
        }

        val accel =
            sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER_UNCALIBRATED)
                ?: sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)

        val gyro =
            sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE_UNCALIBRATED)
                ?: sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        val accelOk = accel?.let { sensorManager.registerListener(imuListener, it, SensorManager.SENSOR_DELAY_FASTEST) } ?: false
        val gyroOk  = gyro?.let  { sensorManager.registerListener(imuListener, it, SensorManager.SENSOR_DELAY_FASTEST) } ?: false
        Log.i("Recorder", "IMU registerListener accelOk=$accelOk gyroOk=$gyroOk")

        camThread = HandlerThread("cam").apply { start() }
        camHandler = Handler(camThread.looper)
        camExecutor = Executor { r -> camHandler.post(r) }

        startCamera()

        return sessionDir
    }

    fun stop() {
        if (!running.getAndSet(false)) return

        try { sensorManager.unregisterListener(imuListener) } catch (_: Throwable) {}
        try { imuOut?.close() } catch (_: Throwable) {}
        imuOut = null

        try { session?.close() } catch (_: Throwable) {}
        try { camera?.close() } catch (_: Throwable) {}
        try { reader?.close() } catch (_: Throwable) {}

        if (::camThread.isInitialized) camThread.quitSafely()

        try { nativeShutdown() } catch (_: Throwable) {}
    }

    @SuppressLint("MissingPermission")
    private fun startCamera() {
        val cm = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager

        val picked = pickCameraIdAndSize(cm, 1280, 720)
        if (picked == null) {
            Log.e("Recorder", "No camera found that supports YUV_420_888")
            return
        }

        val (cameraId, w, h) = picked
        Log.i("Recorder", "Using cameraId=$cameraId size=${w}x$h")

        reader = ImageReader.newInstance(w, h, ImageFormat.YUV_420_888, 4)

        try {
            cm.openCamera(cameraId, camExecutor, object : CameraDevice.StateCallback() {
                override fun onOpened(cd: CameraDevice) {
                    Log.i("Recorder", "Camera opened")
                    camera = cd
                    createSession()
                }
                override fun onDisconnected(cd: CameraDevice) {
                    Log.e("Recorder", "Camera disconnected")
                    cd.close()
                }
                override fun onError(cd: CameraDevice, error: Int) {
                    Log.e("Recorder", "Camera error=$error")
                    cd.close()
                }
            })
        } catch (t: Throwable) {
            Log.e("Recorder", "openCamera threw: ${t.message}", t)
        }
    }

    private fun pickCameraIdAndSize(cm: CameraManager, wantW: Int, wantH: Int): Triple<String, Int, Int>? {
        for (id in cm.cameraIdList) {
            val chars = cm.getCameraCharacteristics(id)
            val map = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP) ?: continue
            val sizes = map.getOutputSizes(ImageFormat.YUV_420_888) ?: continue
            if (sizes.isEmpty()) continue

            sizes.firstOrNull { it.width == wantW && it.height == wantH }?.let {
                return Triple(id, it.width, it.height)
            }

            val under = sizes.filter { it.width <= wantW && it.height <= wantH }
            val chosen = (under.maxByOrNull { it.width * it.height }
                ?: sizes.minByOrNull { it.width * it.height }) ?: continue

            return Triple(id, chosen.width, chosen.height)
        }
        return null
    }

    private fun createSession() {
        val cd = camera ?: return
        val r = reader ?: return

        Log.i("Recorder", "Creating capture session")

        r.setOnImageAvailableListener({ ir ->
            val img = ir.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                Log.i("Recorder", "Got image ts=${img.timestamp}")
                handleFrame(img)
            } catch (t: Throwable) {
                Log.e("Recorder", "handleFrame crashed: ${t.message}", t)
            } finally {
                try { img.close() } catch (_: Throwable) {}
            }
        }, camHandler)

        val outputs = listOf(OutputConfiguration(r.surface))
        val config = SessionConfiguration(
            SessionConfiguration.SESSION_REGULAR,
            outputs,
            camExecutor,
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(cs: CameraCaptureSession) {
                    Log.i("Recorder", "Session configured")
                    session = cs
                    val req = cd.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
                        addTarget(r.surface)
                    }
                    cs.setRepeatingRequest(req.build(), object : CameraCaptureSession.CaptureCallback() {}, camHandler)
                }

                override fun onConfigureFailed(cs: CameraCaptureSession) {
                    Log.e("Recorder", "Session configure failed")
                }
            }
        )

        cd.createCaptureSession(config)
    }

    private fun handleFrame(img: Image) {
        if (!running.get()) return

        val monoNs = System.nanoTime()
        val sensorTimestampNs = img.timestamp

        val (i420, w, h) = imageToI420Safe(img)
        val idx = frameIndex++

        val frameFile = File(camDir, "frame_%06d_i420_%dx%d.bin".format(idx, w, h))
        FileOutputStream(frameFile).use { it.write(i420) }

        val metaFile = File(camDir, "frame_%06d.json".format(idx))
        metaFile.writeText(
            """
            {
              "mono_ns": $monoNs,
              "image_reader_timestamp_ns": $sensorTimestampNs,
              "width": $w,
              "height": $h
            }
            """.trimIndent()
        )
    }

    private fun imageToI420Safe(img: Image): Triple<ByteArray, Int, Int> {
        val w = img.width
        val h = img.height

        val ySize = w * h
        val uvSize = (w * h) / 4
        val out = ByteArray(ySize + uvSize * 2)

        val yPlane = img.planes[0]
        val uPlane = img.planes[1]
        val vPlane = img.planes[2]

        copyPlaneToI420(yPlane, w, h, out, 0)
        copyPlaneToI420(uPlane, w / 2, h / 2, out, ySize)
        copyPlaneToI420(vPlane, w / 2, h / 2, out, ySize + uvSize)

        return Triple(out, w, h)
    }

    private fun copyPlaneToI420(p: Image.Plane, width: Int, height: Int, out: ByteArray, outOffset: Int) {
        val buf = p.buffer
        val rowStride = p.rowStride
        val pixelStride = p.pixelStride
        val limit = buf.limit()

        var outIdx = outOffset

        for (row in 0 until height) {
            val rowStart = row * rowStride
            var inIdx = rowStart

            for (col in 0 until width) {
                if (inIdx >= limit) {
                    outIdx += (width - col) // remaining bytes stay 0
                    break
                }
                out[outIdx++] = buf.get(inIdx)
                inIdx += pixelStride
            }
        }
    }
}
