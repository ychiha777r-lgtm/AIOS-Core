import asyncio

class VaultSecretStore:
    def __init__(self, client, path_template: str = "secret/data/{name}"):
        self.client = client
        self.path_template = path_template

    async def get_secret(self, name: str) -> str:
        # Если используете sync hvac, вызывайте в threadpool
        loop = asyncio.get_running_loop()
        path = self.path_template.format(name=name)
        def _read():
            return self.client.secrets.kv.v2.read_secret_version(path.split("secret/data/")[-1])
        res = await loop.run_in_executor(None, _read)
        # распарсить payload
        return res["data"]["data"].get("value")
