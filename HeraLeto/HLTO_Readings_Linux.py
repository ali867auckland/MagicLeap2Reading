import asyncio
from bleak import BleakScanner
from datetime import datetime

TARGET_MAC = "C0:22:19:03:01:CC" 

def advertisement_callback(device, advertisement_data):
    """
    Processes BLE advertisement packets and filters based on the target device.
    """
    if TARGET_MAC and device.address != TARGET_MAC:
        return  # Ignore devices that don't match the MAC address
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{current_time}]")
    print(f"\nFound Target Device: {device.address} - {device.name}")
    print(f"RSSI: {advertisement_data.rssi} dBm")

    if advertisement_data.manufacturer_data:
        for manufacturer_id, raw_data in advertisement_data.manufacturer_data.items():
            hex_data = raw_data.hex()
            print(f"Manufacturer ID: {manufacturer_id} | Raw Data: {hex_data}")

            if len(raw_data) >= 12:
                heart_rate = raw_data[3]  
                respiration_rate = raw_data[5]  
                temperature = int.from_bytes(raw_data[10:12], byteorder="little") / 100.0  
                spo2 = raw_data[-5]
                if spo2 == 151:
                    spo2 = "Still reading for Sp02"

                print(f"Heart Rate: {heart_rate} bpm")
                print(f"Respiration Rate: {respiration_rate} breaths/min")
                print(f"Temperature: {temperature:.2f} °C")
                print(f"SpO₂: {spo2}%")

async def scan_ble():
    """
    Continuously scans for BLE advertisements until manually stopped.
    """
    print("🔍 Scanning for BLE advertisements (Press Ctrl+C to stop)...")
    scanner = BleakScanner(detection_callback=advertisement_callback)
    
    while True:  # Infinite loop
        try:
            await scanner.start()
            await asyncio.sleep(5)  # Adjust sleep time for interval scanning
            await scanner.stop()
        except asyncio.CancelledError:
            break  # Exit gracefully if the script is stopped
        except Exception as e:
            print(f"⚠️ Error: {e}, retrying...")
            await asyncio.sleep(2)  # Wait before retrying

    print("🔴 Stopping BLE scanning.")

if __name__ == "__main__":
    try:
        asyncio.run(scan_ble())  # Runs until manually stopped
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
