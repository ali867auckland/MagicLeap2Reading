import asyncio
from datetime import datetime
import csv
import os

from bleak import BleakScanner, BleakClient

# Match the BLE name you saw: "HLTO - 01CC"
TARGET_NAME_KEYWORD = "HLTO"

# CSV file names (will be created in the current working directory)
REP_CSV = "hera_repdat1.csv"
SPO2_CSV = "hera_spo2.csv"
HR_TEMP_CSV = "hera_hr_temp.csv"


def open_csv(path: str, header=None):
    """
    Open a CSV for appending.
    If the file is new/empty and a header is provided, write the header row.
    """
    file_exists = os.path.exists(path)
    f = open(path, "a", newline="", encoding="utf-8")
    writer = csv.writer(f)
    if (not file_exists or os.path.getsize(path) == 0) and header is not None:
        writer.writerow(header)
    return f, writer


def make_notification_handler(
    char_uuid: str,
    rep_writer=None,
    spo2_writer=None,
    hrtemp_writer=None,
):
    CUSTOM_LOG_UUID = "40af0003-9479-43f6-ae95-c45fb2afb9d2"
    HR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
    TEMP_UUID = "00002a1c-0000-1000-8000-00805f9b34fb"

    def handler(sender: int, data: bytearray):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # 1) Vendor-specific Hera Leto DSP text stream
        if char_uuid == CUSTOM_LOG_UUID:
            text = data.decode("ascii", errors="ignore")
            print(f"\n[{ts}] {char_uuid} (DSP log)")

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                print("  ", line)

                # 1a) SpO2 lines, e.g. "[DSP]SpO2 : -39.18 118.48"
                if line.startswith("[DSP]SpO2") and spo2_writer is not None:
                    try:
                        after = line.split(":", 1)[1].strip()
                        parts = after.split()
                        # Only grab the first two numeric tokens for now
                        val1 = parts[0] if len(parts) > 0 else ""
                        val2 = parts[1] if len(parts) > 1 else ""
                        spo2_writer.writerow([ts, val1, val2, line])
                    except Exception as e:
                        print("    (SpO2 parse error:", e, ")")

                # 1b) REP_DAT1 records
                if line.startswith("REP_DAT1") and rep_writer is not None:
                    try:
                        _, csv_part = line.split(" ", 1)
                        fields = [f.strip() for f in csv_part.split(",") if f.strip() != ""]
                        device_ts = fields[0] if fields else ""
                        # Join the rest back into a single string; we’ll decode later
                        rest = ",".join(fields[1:]) if len(fields) > 1 else ""
                        rep_writer.writerow([ts, device_ts, rest])
                    except Exception as e:
                        print("    (REP_DAT1 parse error:", e, ")")

        # 2) Standard Heart Rate Measurement (0x2A37)
        elif char_uuid == HR_UUID:
            flags = data[0] if len(data) > 0 else 0
            heart_rate = None

            if len(data) >= 2:
                if (flags & 0x01) and len(data) >= 3:
                    # 16-bit HR
                    heart_rate = int.from_bytes(data[1:3], byteorder="little")
                else:
                    # 8-bit HR
                    heart_rate = data[1]

            print(f"\n[{ts}] HeartRate: {heart_rate} bpm  (raw: {list(data)})")

            if hrtemp_writer is not None and heart_rate is not None:
                hrtemp_writer.writerow([ts, "hr", heart_rate])

        # 3) Standard Temperature Measurement (0x2A1C)
        elif char_uuid == TEMP_UUID:
            print(f"\n[{ts}] Temp raw: {list(data)} (hex {data.hex()})")

            if hrtemp_writer is not None:
                # Just log hex for now; we’ll decode to °C later
                hrtemp_writer.writerow([ts, "temp_raw", data.hex()])

        # 4) Any other notifiable characteristic -> debug-only
        else:
            print(f"\n[{ts}] {char_uuid}")
            print("  ints:", list(data))
            print("  hex :", data.hex())

    return handler


async def find_hlto(timeout: float = 8.0):
    print(f"Scanning for {timeout} seconds...")
    devices = await BleakScanner.discover(timeout=timeout)

    candidate = None
    for d in devices:
        print(d.address, d.name)
        name = d.name or ""
        if TARGET_NAME_KEYWORD.lower() in name.lower():
            candidate = d

    if candidate is None:
        print("Could not find any device with name containing:", TARGET_NAME_KEYWORD)
        return None

    print(f"\nUsing device: {candidate.name} ({candidate.address})")
    return candidate


async def run():
    device = await find_hlto()
    if device is None:
        return

    # --- Open CSV files for logging ---
    rep_file, rep_writer = open_csv(
        REP_CSV,
        header=["pc_time", "device_ts", "values"],
    )
    spo2_file, spo2_writer = open_csv(
        SPO2_CSV,
        header=["pc_time", "val1", "val2", "raw_line"],
    )
    hrtemp_file, hrtemp_writer = open_csv(
        HR_TEMP_CSV,
        header=["pc_time", "type", "value"],
    )

    print("\nConnecting with BleakClient...")
    async with BleakClient(device) as client:
        print("Connected:", client.is_connected)

        print("Discovering services and characteristics...")

        # Newer bleak has get_services(), older versions keep services on client.services.
        if hasattr(client, "get_services"):
            services = await client.get_services()
        else:
            services = client.services

        if services is None:
            print("Could not obtain GATT services from the client.")
            return

        notifiable_chars = []
        for service in services:
            for char in service.characteristics:
                if "notify" in char.properties:
                    notifiable_chars.append(char)

        if not notifiable_chars:
            print("No notifiable characteristics found.")
            return

        print("\nSubscribing to these characteristics:")
        for char in notifiable_chars:
            print(
                f"  Service {char.service_uuid} | Char {char.uuid} "
                f"| Props {char.properties}"
            )
            handler = make_notification_handler(
                char.uuid,
                rep_writer=rep_writer,
                spo2_writer=spo2_writer,
                hrtemp_writer=hrtemp_writer,
            )
            await client.start_notify(char.uuid, handler)

        print("\nNow listening for data... Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            print("Stopping notifications...")
        finally:
            # Stop notifications
            for char in notifiable_chars:
                try:
                    await client.stop_notify(char.uuid)
                except Exception:
                    pass

            # Close CSV files
            rep_file.close()
            spo2_file.close()
            hrtemp_file.close()


if __name__ == "__main__":
    asyncio.run(run())
