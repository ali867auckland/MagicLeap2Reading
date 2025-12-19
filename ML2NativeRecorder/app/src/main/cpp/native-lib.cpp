#include <jni.h>
#include <android/log.h>
#include <mutex>

#include "ml_perception.h"
#include "ml_head_tracking.h"
#include "ml_snapshot.h"
#include "ml_time.h"

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  "native-lib", __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, "native-lib", __VA_ARGS__)

static std::mutex g_mu;
static bool g_ready = false;
static MLHandle g_head = ML_INVALID_HANDLE;
static MLCoordinateFrameUID g_head_cf{};

static void LogML(const char* what, MLResult r) {
    if (r == MLResult_Ok) {
        LOGI("%s OK", what);
    } else {
        // Perception module provides this string helper:
        // MLSnapshotGetResultString(result_code) :contentReference[oaicite:2]{index=2}
        LOGE("%s failed: r=%d (%s)", what, (int)r, MLSnapshotGetResultString(r));
    }
}

extern "C"
JNIEXPORT jstring JNICALL
Java_com_example_ml2nativerecorder_MainActivity_stringFromJNI(JNIEnv* env, jobject) {
    return env->NewStringUTF("Hello from native C++");
}

extern "C"
JNIEXPORT jboolean JNICALL
Java_com_example_ml2nativerecorder_Recorder_nativeInit(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lk(g_mu);
    if (g_ready) return JNI_TRUE;

    MLPerceptionSettings s{};
    MLResult r = MLPerceptionInitSettings(&s);
    LogML("MLPerceptionInitSettings", r);
    if (r != MLResult_Ok) return JNI_FALSE;

    r = MLPerceptionStartup(&s);
    LogML("MLPerceptionStartup", r);
    if (r != MLResult_Ok) return JNI_FALSE;

    r = MLHeadTrackingCreate(&g_head);
    LogML("MLHeadTrackingCreate", r);
    if (r != MLResult_Ok || g_head == ML_INVALID_HANDLE) return JNI_FALSE;

    MLHeadTrackingStaticData sd{};
    r = MLHeadTrackingGetStaticData(g_head, &sd);
    LogML("MLHeadTrackingGetStaticData", r);
    if (r != MLResult_Ok) return JNI_FALSE;

    g_head_cf = sd.coord_frame_head;

    g_ready = true;
    LOGI("nativeInit OK");
    return JNI_TRUE;
}

extern "C"
JNIEXPORT void JNICALL
Java_com_example_ml2nativerecorder_Recorder_nativeShutdown(JNIEnv*, jobject) {
    std::lock_guard<std::mutex> lk(g_mu);
    if (!g_ready) return;

    if (g_head != ML_INVALID_HANDLE) {
        MLHeadTrackingDestroy(g_head);
        g_head = ML_INVALID_HANDLE;
    }
    MLResult r = MLPerceptionShutdown();
    LogML("MLPerceptionShutdown", r);

    g_ready = false;
    LOGI("nativeShutdown OK");
}

extern "C"
JNIEXPORT jfloatArray JNICALL
Java_com_example_ml2nativerecorder_Recorder_nativePoseAtMLTime(JNIEnv* env, jobject, jlong ml_time) {
    std::lock_guard<std::mutex> lk(g_mu);

    jfloatArray out = env->NewFloatArray(16);
    float buf[16]{};

    if (!g_ready) {
        env->SetFloatArrayRegion(out, 0, 16, buf);
        return out;
    }

    MLSnapshot* snap = nullptr;
    MLResult r = MLPerceptionGetPredictedSnapshot((MLTime)ml_time, &snap);
    if (r != MLResult_Ok || !snap) {
        LogML("MLPerceptionGetPredictedSnapshot", r);
        env->SetFloatArrayRegion(out, 0, 16, buf);
        return out;
    }

    MLTransform t{};
    MLTransformDerivatives d{};
    r = MLSnapshotGetTransformWithDerivatives(snap, &g_head_cf, &t, &d);
    MLPerceptionReleaseSnapshot(snap);

    if (r != MLResult_Ok) {
        LogML("MLSnapshotGetTransformWithDerivatives", r);
        env->SetFloatArrayRegion(out, 0, 16, buf);
        return out;
    }

    buf[0] = t.position.x;
    buf[1] = t.position.y;
    buf[2] = t.position.z;
    buf[3] = t.rotation.x;
    buf[4] = t.rotation.y;
    buf[5] = t.rotation.z;
    buf[6] = t.rotation.w;

    buf[7]  = d.linear_velocity_m_s.x;
    buf[8]  = d.linear_velocity_m_s.y;
    buf[9]  = d.linear_velocity_m_s.z;
    buf[10] = d.angular_velocity_r_s.x;
    buf[11] = d.angular_velocity_r_s.y;
    buf[12] = d.angular_velocity_r_s.z;

    buf[13] = 1.0f; // placeholder

    env->SetFloatArrayRegion(out, 0, 16, buf);
    return out;
}
