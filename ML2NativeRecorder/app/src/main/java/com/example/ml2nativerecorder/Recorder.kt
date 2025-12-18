package com.example.ml2nativerecorder

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.camera2.*
import android.media.Image
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executor
import java.util.concurrent.atomic.AtomicBoolean
import android.hardware.camera2.params.OutputConfiguration
import android.hardware.camera2.params.SessionConfiguration


class Recorder(private val ctx: Context) {

    companion object {
        init { System.loadLibrary("native-lib") }

        // ML2 vendor tags (from ml_camera_vendor_tags.h)
        private val KEY_CVIP_MLTIME = CaptureResult.Key<LongArray>(
            "com.amd.control.cvip_timestamps",
            LongArray::class.java
        )

        private val KEY_INTRINSICS = CaptureResult.Key<FloatArray>(
            "com.amd.control.intrinsics",
            FloatArray::class.java
        )
    }

    private external fun nativeInit(): Boolean
    private external fun nativeShutdown()
    private external fun nativePoseAtMLTime(mlTime: Long): FloatArray

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

        sessionDir = File(ctx.getExternalFilesDir(null), "sessions/${System.currentTimeMillis()}")
        camDir = File(sessionDir, "cam").apply { mkdirs() }
        imuFile = File(sessionDir, "imu.csv")
        sessionDir.mkdirs()

        // Init native perception/head pose
        check(nativeInit()) { "nativeInit failed" }

        // Start IMU logging
        sensorManager = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        imuOut = FileOutputStream(imuFile, true).also {
            it.write("mono_ns,sensor_ts_ns,type,values\n".toByteArray())
        }
        val accel = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER_UNCALIBRATED)
        val gyro = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE_UNCALIBRATED)
        sensorManager.registerListener(imuListener, accel, SensorManager.SENSOR_DELAY_FASTEST)
        sensorManager.registerListener(imuListener, gyro, SensorManager.SENSOR_DELAY_FASTEST)

        // Start camera thread
        camThread = HandlerThread("cam").apply { start() }
        camHandler = Handler(camThread.looper)

        // ✅ Executor that posts back onto the same camera thread (removes deprecated Handler overload warning)
        camExecutor = Executor { r -> camHandler.post(r) }

        startCamera()

        return sessionDir
    }

    fun stop() {
        if (!running.getAndSet(false)) return

        sensorManager.unregisterListener(imuListener)
        imuOut?.close()
        imuOut = null

        try { session?.close() } catch (_: Throwable) {}
        try { camera?.close() } catch (_: Throwable) {}
        try { reader?.close() } catch (_: Throwable) {}

        if (::camThread.isInitialized) camThread.quitSafely()

        nativeShutdown()
    }

    @SuppressLint("MissingPermission")
    private fun startCamera() {
        val cm = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager

        // ML2 camera IDs include "0", "1", "3". We use "1" to avoid MR camera conflicts.
        val cameraId = "1"

        // Choose a conservative size. (You can query characteristics and pick bigger.)
        reader = ImageReader.newInstance(1280, 720, android.graphics.ImageFormat.YUV_420_888, 4)

        cm.openCamera(cameraId, camExecutor, object : CameraDevice.StateCallback() {
            override fun onOpened(cd: CameraDevice) {
                camera = cd
                createSession()
            }
            override fun onDisconnected(cd: CameraDevice) { cd.close() }
            override fun onError(cd: CameraDevice, error: Int) { cd.close() }
        })
    }

    private fun createSession() {
        val cd = camera ?: return
        val r = reader ?: return

        r.setOnImageAvailableListener({ ir ->
            val img = ir.acquireLatestImage() ?: return@setOnImageAvailableListener
            handleFrame(img)
            img.close()
        }, camHandler)

        val outputs = listOf(OutputConfiguration(r.surface))

        val config = SessionConfiguration(
            SessionConfiguration.SESSION_REGULAR,
            outputs,
            camExecutor, // Executor (not Handler)
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(cs: CameraCaptureSession) {
                    session = cs
                    val req = cd.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
                        addTarget(r.surface)
                    }
                    cs.setRepeatingRequest(req.build(), captureCb, camHandler)
                }

                override fun onConfigureFailed(cs: CameraCaptureSession) {}
            }
        )

        cd.createCaptureSession(config)
    }


    private val captureCb = object : CameraCaptureSession.CaptureCallback() {
        override fun onCaptureCompleted(
            session: CameraCaptureSession,
            request: CaptureRequest,
            result: TotalCaptureResult
        ) {
            // Optional: read metadata here if you store TotalCaptureResult for MLTime extraction.
        }
    }

    private fun handleFrame(img: Image) {
        if (!running.get()) return
        val monoNs = System.nanoTime()

        val sensorTimestampNs = img.timestamp // frame timestamp from ImageReader (nanoseconds)

        val (i420, w, h) = imageToI420(img)
        val idx = frameIndex++
        val frameFile = File(camDir, "frame_%06d_i420_%dx%d.bin".format(idx, w, h))
        FileOutputStream(frameFile).use { it.write(i420) }

        val metaFile = File(camDir, "frame_%06d.json".format(idx))
        val json = """
          {
            "mono_ns": $monoNs,
            "image_reader_timestamp_ns": $sensorTimestampNs,
            "width": $w,
            "height": $h
          }
        """.trimIndent()
        metaFile.writeText(json)
    }

    private fun imageToI420(img: Image): Triple<ByteArray, Int, Int> {
        val w = img.width
        val h = img.height
        val y = img.planes[0]
        val u = img.planes[1]
        val v = img.planes[2]

        val out = ByteArray(w * h + (w * h / 2))
        var offset = 0

        // Y
        copyPlane(y, w, h, out, offset)
        offset += w * h

        // U then V in I420
        val uBytes = extractChromaPlane(u, w, h)
        val vBytes = extractChromaPlane(v, w, h)
        System.arraycopy(uBytes, 0, out, offset, uBytes.size); offset += uBytes.size
        System.arraycopy(vBytes, 0, out, offset, vBytes.size)

        return Triple(out, w, h)
    }

    private fun copyPlane(p: Image.Plane, w: Int, h: Int, out: ByteArray, outOffset: Int) {
        val rowStride = p.rowStride
        val buf = p.buffer
        var off = outOffset
        val row = ByteArray(rowStride)
        for (r in 0 until h) {
            buf.position(r * rowStride)
            buf.get(row, 0, rowStride)
            System.arraycopy(row, 0, out, off, w)
            off += w
        }
    }

    private fun extractChromaPlane(p: Image.Plane, w: Int, h: Int): ByteArray {
        val cw = w / 2
        val ch = h / 2
        val out = ByteArray(cw * ch)

        val rowStride = p.rowStride
        val pixelStride = p.pixelStride
        val buf = p.buffer

        var outIdx = 0
        val row = ByteArray(rowStride)
        for (r in 0 until ch) {
            buf.position(r * rowStride)
            buf.get(row, 0, rowStride)
            var c = 0
            while (c < cw) {
                out[outIdx++] = row[c * pixelStride]
                c++
            }
        }
        return out
    }
}
