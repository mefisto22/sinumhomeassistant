import aiohttp

class SinumAPI:
    def __init__(self, ip, token):
        self.base_url = f"http://{ip}/api"
        self.headers = {"Authorization": f"Bearer {token}"}

    async def get_virtual_devices(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/virtual-devices", headers=self.headers) as response:
                response.raise_for_status()
                return await response.json()