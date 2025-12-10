import sys
import pandas as pd
import matplotlib.pyplot as plt

def main():
    # 1) Get CSV path from command line
    if len(sys.argv) < 2:
        print("Usage: python plot_imu_csv.py path/to/imu.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    print(f"Loading {csv_path} ...")

    # 2) Load CSV
    df = pd.read_csv(csv_path)

    # Rename your headers to the names we expect in the plotting code
    df = df.rename(columns={
        "accx": "acc_x",
        "accy": "acc_y",
        "accz": "acc_z",
        "gyrox": "gyro_x",
        "gyroy": "gyro_y",
        "gyroz": "gyro_z",
        "magx": "mag_x",
        "magy": "mag_y",
        "magz": "mag_z",
    })

    required_cols = [
        "t_ns",
        "acc_x", "acc_y", "acc_z",
        "gyro_x", "gyro_y", "gyro_z",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in CSV. Found columns: {df.columns.tolist()}")

    # 3) Time axis in seconds relative to start
    t0 = df["t_ns"].iloc[0]
    df["t_s"] = (df["t_ns"] - t0) / 1e9

    # 4) Plot accelerometer
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(10, 8))

    ax_acc = axes[0]
    ax_acc.plot(df["t_s"], df["acc_x"], label="acc_x")
    ax_acc.plot(df["t_s"], df["acc_y"], label="acc_y")
    ax_acc.plot(df["t_s"], df["acc_z"], label="acc_z")
    ax_acc.set_ylabel("Acceleration [g-ish]")
    ax_acc.set_title("Accelerometer")
    ax_acc.legend()
    ax_acc.grid(True)

    # 5) Plot gyro
    ax_gyro = axes[1]
    ax_gyro.plot(df["t_s"], df["gyro_x"], label="gyro_x")
    ax_gyro.plot(df["t_s"], df["gyro_y"], label="gyro_y")
    ax_gyro.plot(df["t_s"], df["gyro_z"], label="gyro_z")
    ax_gyro.set_ylabel("Gyro [rad/s]")
    ax_gyro.set_xlabel("Time [s]")
    ax_gyro.set_title("Gyroscope")
    ax_gyro.legend()
    ax_gyro.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
