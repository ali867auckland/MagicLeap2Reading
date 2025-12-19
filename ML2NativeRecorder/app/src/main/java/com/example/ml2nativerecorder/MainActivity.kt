package com.example.ml2nativerecorder

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.widget.TextView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : Activity() {

    private lateinit var recorder: Recorder
    private lateinit var status: TextView

    private val REQ_CAMERA = 1001

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        status = TextView(this).apply {
            text = "Starting…"
            textSize = 16f
            setPadding(24, 24, 24, 24)
        }
        setContentView(status)

        recorder = Recorder(this)

        ensureCameraPermissionAndStart()
    }

    private fun ensureCameraPermissionAndStart() {
        val hasCamera = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED

        if (!hasCamera) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
            status.text = "Requesting Camera permission…"
            return
        }

        val dir = recorder.start()
        Log.i("MainActivity", "Recording to: ${dir.absolutePath}")
        status.text = "Recording to:\n${dir.absolutePath}\n\n(Leave app open to record)"
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)

        if (requestCode == REQ_CAMERA) {
            val granted = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
            if (granted) {
                ensureCameraPermissionAndStart()
            } else {
                status.text = "Camera permission denied. Cannot record camera frames."
            }
        }
    }

    override fun onDestroy() {
        try { recorder.stop() } catch (_: Throwable) {}
        super.onDestroy()
    }
}
