import asyncio
from datetime import datetime

from bleak import BleakScanner, BleakClient

# We’ll match by name instead of hard-coding the address
TARGET_NAME_KEYWORD = "HLTO"   # matches "HLTO - 01CC"


def make_notification_handler(char_uuid: str):
    def handler(sender: int, data: bytearray):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        int_view = list(data)
        hex_view = data.hex()
        print(f"\n[{ts}] {char_uuid}")
        print(f"  ints: {int_view}")
        print(f"  hex : {hex_view}")
    return handler


async def find_hlto_device(timeout: float = 10.0):
    """
    Scan for BLE devices and return the Bleak device object
    whose name contains TARGET_NAME_KEYWORD.
    """
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
    # 1) Find the HLTO device object
    device = await find_hlto_device()
    if device is None:
        return

    # 2) Connect using the device object (more robust on Windows)
    print("\nConnecting with BleakClient...")
    async with BleakClient(device, timeout=30.0, pair=True) as client:
        print("Connected:", client.is_connected)

        print("Discovering services and characteristics...")
        services = await client.get_services()

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

        for char in notifiable_chars:
            await client.start_notify(char.uuid, make_notification_handler(char.uuid))

        print("\nNow listening for data... Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            print("Stopping notifications...")

        for char in notifiable_chars:
            try:
                await client.stop_notify(char.uuid)
            except Exception:
                pass

        print("Done.")


if __name__ == "__main__":
    asyncio.run(run())
