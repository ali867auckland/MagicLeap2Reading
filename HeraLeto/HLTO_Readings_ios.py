import asyncio
from datetime import datetime

from bleak import BleakScanner, BleakClient

# Match the BLE name you saw: "HLTO - 01CC"
TARGET_NAME_KEYWORD = "HLTO"


def make_notification_handler(char_uuid: str):
    def handler(sender: int, data: bytearray):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        int_view = list(data)
        hex_view = data.hex()
        print(f"\n[{ts}] {char_uuid}")
        print(f"  ints: {int_view}")
        print(f"  hex : {hex_view}")
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

    print("\nConnecting with BleakClient...")
    async with BleakClient(device) as client:
        print("Connected:", client.is_connected)

        print("Discovering services and characteristics...")

        # Newer bleak has get_services(), older versions keep services on client.services.
        if hasattr(client, "get_services"):
            # If this exists, use the async method
            services = await client.get_services()
        else:
            # Fallback: use the services property
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
            await client.start_notify(char.uuid, make_notification_handler(char.uuid))

        print("\nNow listening for data... Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            print("Stopping notifications...")
        finally:
            for char in notifiable_chars:
                try:
                    await client.stop_notify(char.uuid)
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(run())
