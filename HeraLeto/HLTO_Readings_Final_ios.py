import asyncio
from bleak import BleakScanner
from datetime import datetime
import csv
import os

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
# Filter by *name* so it works on macOS (where BLE "MACs" are long UUIDs)
TARGET_NAME_KEYWORD = "HLTO"      # matches "HLTO - 01CC", etc.
TARGET_ADDRESS = None             # keep as None to rely on name only

CSV_PATH = "hera_advert_metrics.csv"

# Globals for CSV writer so the callback can use them
csv_file = None
csv_writer = None


# ----------------------------------------------------------------------
# CSV HELPERS
# ----------------------------------------------------------------------
def init_csv(path: str):
    """Open CSV for appending, write header if file is new/empty."""
    global csv_file, csv_writer
    file_exists = os.path.exists(path)

    csv_file = open(path, "a", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)

    if not file_exists or os.path.getsize(path) == 0:
        csv_writer.writerow([
            "pc_time",          # local time on this machine
            "device_name",
            "device_address",
            "rssi_dbm",
            "heart_rate_bpm",
            "respiration_rate_bpm",
            "temperature_c",
            "spo2_pct",
            "manufacturer_id",
            "raw_hex"
        ])


def close_csv():
    global csv_file
    if csv_file is not None:
        csv_file.close()
        csv_file = None


# ----------------------------------------------------------------------
# ADVERTISEMENT CALLBACK
# ----------------------------------------------------------------------
def advertisement_callback(device, advertisement_data):
    """
    Called every time Bleak sees an advertisement.
    We filter by device name and decode Hera Leto vital-signs from
    manufacturer_data.
    """
    # 1) Filter by name keyword (recommended on macOS)
    name = device.name or ""
    if TARGET_NAME_KEYWORD and TARGET_NAME_KEYWORD.lower() not in name.lower():
        return

    # 2) Optional second filter by address (leave TARGET_ADDRESS=None on macOS)
    if TARGET_ADDRESS and device.address != TARGET_ADDRESS:
        return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    rssi = advertisement_data.rssi

    if not advertisement_data.manufacturer_data:
        return

    for manufacturer_id, raw_data in advertisement_data.manufacturer_data.items():
        hex_data = raw_data.hex()

        heart_rate = None
        respiration_rate = None
        temperature = None
        spo2 = None

        # Hera Leto payload layout (from your original final.py):
        #   raw_data[3]      -> heart rate (bpm)
        #   raw_data[5]      -> respiration rate (breaths/min)
        #   raw_data[10:12]  -> temp * 100, little-endian (°C)
        #   raw_data[-5]     -> SpO2 (%), 151 means "still reading"
        if len(raw_data) >= 12:
            heart_rate = raw_data[3]
            respiration_rate = raw_data[5]
            temperature = int.from_bytes(raw_data[10:12], byteorder="little") / 100.0

            spo2_val = raw_data[-5]
            # In your original script, 151 meant "Still reading for SpO2"
            spo2 = None if spo2_val == 151 else spo2_val

        # Console debug output
        print(f"\n[{current_time}] {device.address} ({name})  RSSI {rssi} dBm")
        print("  Manufacturer ID:", manufacturer_id)
        print("  Raw:", hex_data)
        print(f"  HR : {heart_rate} bpm")
        print(f"  RR : {respiration_rate} breaths/min")
        print(f"  Temp: {temperature} °C")
        print(f"  SpO2: {spo2 if spo2 is not None else 'Still reading / unknown'}")

        # CSV logging
        if csv_writer is not None:
            csv_writer.writerow([
                current_time,
                name,
                device.address,
                rssi,
                heart_rate if heart_rate is not None else "",
                respiration_rate if respiration_rate is not None else "",
                f"{temperature:.2f}" if temperature is not None else "",
                spo2 if spo2 is not None else "",
                manufacturer_id,
                hex_data,
            ])


# ----------------------------------------------------------------------
# MAIN SCAN LOOP
# ----------------------------------------------------------------------
async def scan_ble():
    """
    Continuously scans for BLE advertisements until manually stopped.
    """
    print("🔍 Scanning for Hera Leto BLE advertisements (Press Ctrl+C to stop)...")
    init_csv(CSV_PATH)

    scanner = BleakScanner(detection_callback=advertisement_callback)

    try:
        while True:
            try:
                await scanner.start()
                await asyncio.sleep(5.0)  # scan chunk
                await scanner.stop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Error: {e}, retrying in 2s...")
                await asyncio.sleep(2.0)
    finally:
        print("🔴 Stopping BLE scanning.")
        close_csv()


if __name__ == "__main__":
    try:
        asyncio.run(scan_ble())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
        close_csv()
