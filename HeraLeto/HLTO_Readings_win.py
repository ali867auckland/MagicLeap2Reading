import asyncio
from datetime import datetime

from bleak import BleakClient

HERA_ADDRESS = "C0:22:19:03:01:CC" 


def notification_handler(char_uuid: str):
    """
    Returns a handler function to process notifications from the char_uuid through BLE.
    Where the handler function will remember the specified char_uuid.
    """
    def handler(sender: int, data: bytearray):
        """
        Handles incoming notifications from the BLE device.
        """
        # time with milliseconds, but human-readable
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # trim to ms

        # two views of the same bytes
        int_view = list(data)
        hex_view = data.hex()

        print(f"\n[{ts}] {char_uuid}")
        print(f"  ints: {int_view}")
        print(f"  hex : {hex_view}")
    return handler

async def run():
    print(f"🔌 Connecting to Hera Leto at {HERA_ADDRESS}...")

    async with BleakClient(HERA_ADDRESS) as client:
        print("✅ Connected.", client.is_connected) # Confirms Connection

        services = await client.get_services() # Discover services

        notifiable_chars = []
        for service in services: # Iterates through services
            for char in service.characteristics: # Iterates through characteristics
                if "notify" in char.properties: # Checks for notify property
                    notifiable_chars.append(char) 
        
        # If no notifiable characteristics are found, exit early
        if not notifiable_chars:
            print("⚠️ No notifiable characteristics found!")
            return
        
        """
        for char in notifiable_chars:
            print(
                f" Service: {char.service_uuid} | Characteristic: {char.uuid} 
                | Properties: {char.properties}")
        """

        for char in notifiable_chars:
            await client.start_notify(char.uuid, notification_handler(char.uuid))

        try:
            while True:
                await asyncio.sleep(1)  # Keep the script running to receive notifications
        except KeyboardInterrupt:
            print("🔴 Stopping notifications...")
        
        for char in notifiable_chars:
            try:
                await client.stop_notify(char.uuid)
            except Exception:
                pass 

if __name__ == "__main__":
    asyncio.run(run())
        
