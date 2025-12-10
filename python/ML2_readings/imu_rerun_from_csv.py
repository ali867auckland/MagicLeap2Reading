import rerun as rr
import pandas as pd
import numpy as np


def main():
    print("Loading imu.csv ...")
    df = pd.read_csv("imu.csv")
    print("Columns:", df.columns.tolist())

    # Start Rerun and spawn the viewer window
    rr.init("ML2 IMU replay", spawn=True)

    # Declare a world coordinate frame (optional but nice)
    rr.log("world", rr.CoordinateFrame("world"))

    for _, row in df.iterrows():
        t_ns = int(row["t_ns"])

        # This is deprecated but still works; warning is safe to ignore for now.
        rr.set_time_nanos("time", t_ns)

        # Use Scalars instead of Scalar (batch of length 1)
        rr.log("imu/acc/x", rr.Scalars(np.array([row["accx"]], dtype=float)))
        rr.log("imu/acc/y", rr.Scalars(np.array([row["accy"]], dtype=float)))
        rr.log("imu/acc/z", rr.Scalars(np.array([row["accz"]], dtype=float)))

        rr.log("imu/gyro/x", rr.Scalars(np.array([row["gyrox"]], dtype=float)))
        rr.log("imu/gyro/y", rr.Scalars(np.array([row["gyroy"]], dtype=float)))
        rr.log("imu/gyro/z", rr.Scalars(np.array([row["gyroz"]], dtype=float)))

        # If you want mag later:
        # rr.log("imu/mag/x", rr.Scalars(np.array([row["magx"]], dtype=float)))
        # rr.log("imu/mag/y", rr.Scalars(np.array([row["magy"]], dtype=float)))
        # rr.log("imu/mag/z", rr.Scalars(np.array([row["magz"]], dtype=float)))


if __name__ == "__main__":
    main()
