import json
from app.core.config import config
from app.core.http_client import HttpClient, HttpConfig


class GatewayServer:
    def __init__(self):
        self.server = HttpClient(
            f"{config.get('server.protocol')}://{config.get('server.host')}:{config.get('server.port')}/api/",
            config=HttpConfig(timeout=config.get("server.timeout", 3600))
        )
        self.id = config.get("app.id")
    
    async def register(self):
        response = await self.server.post("gateway/register", json={
            "id": config.get("app.id"),
            "port": config.get("app.port"),
        })
        if response.get("code") == 200:
            return response.get("data")
        else:
            raise Exception(f"网关注册失败: {json.dumps(response, ensure_ascii=False)}")
        
    async def unregister(self):
        response = await self.server.put(f"gateway/{config.get('app.id')}", json={ "status": 0 })
        if response.get("code") == 200:
            return response.get("data")
        else:
            raise Exception(f"网关注销失败: {json.dumps(response, ensure_ascii=False)}")
        
    async def nds_list(self):
        response = await self.server.get(f"/gateway/{config.get('app.id')}")
        print(f"获取到NDS列表: {json.dumps(response, ensure_ascii=False)}")
        if response.get("code") == 200:
            return response.get("data").get("ndsLinks", [])
        else:
            raise Exception(f"获取NDS失败: {json.dumps(response, ensure_ascii=False)}")
        
    