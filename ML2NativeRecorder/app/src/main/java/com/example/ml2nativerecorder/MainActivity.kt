package com.example.ml2nativerecorder

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log

class MainActivity : Activity() {

    private var recorder: Recorder? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        recorder = Recorder(this)
        val dir = recorder!!.start()
        Log.i("ML2NativeRecorder", "Recording to: ${dir.absolutePath}")

        // Auto-stop after 10 seconds (adjust as you like)
        Handler(Looper.getMainLooper()).postDelayed({
            recorder?.stop()
            Log.i("ML2NativeRecorder", "Stopped. Files are in: ${dir.absolutePath}")
        }, 10_000)
    }

    override fun onDestroy() {
        recorder?.stop()
        super.onDestroy()
    }
}
