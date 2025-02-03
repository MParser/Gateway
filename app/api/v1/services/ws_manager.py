from typing import Dict
import asyncio
import time
from fastapi import WebSocket
from app.core.logger import log
from app.api.v1.models.ws_models import WS_RESPONSE, WSMessageType


# noinspection PyBroadException
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.chunk_size = 524288  # 512KB
        self.lock = asyncio.Lock()
        self.check_interval = 30
        self.check_failures: Dict[str, int] = {}
        self.max_failures = 3
        self._check_task = asyncio.create_task(self._check_all_connections())
        log.info("连接检查任务已启动")

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        async with self.lock:
            if client_id in self.active_connections:
                await self.disconnect(client_id)
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.check_failures.pop(client_id, None)
            log.debug(f"客户端[{client_id}]连接成功")

    async def disconnect(self, client_id: str) -> None:
        async with self.lock:
            if websocket := self.active_connections.pop(client_id, None):
                try:
                    await websocket.close()
                except Exception:
                    pass
            self.check_failures.pop(client_id, None)
            log.debug(f"客户端[{client_id}]已断开")

    async def send_response(self, client_id: str, response: WS_RESPONSE) -> bool:
        """
        发送WebSocket响应
        
        :param client_id: 客户端ID
        :param response: 响应对象，必须是 WS_RESPONSE 类型
        :return: 发送是否成功
        """
        if websocket := self.active_connections.get(client_id):
            try:
                await websocket.send_json(response.model_dump())
                return True
            except Exception as e:
                log.error(f"发送响应失败[{client_id}]: {str(e)}")
        return False

    async def send_file(self, client_id: str, data: bytes, request_id: str) -> bool:
        if not (websocket := self.active_connections.get(client_id)):
            return False

        try:
            response = WS_RESPONSE(type=WSMessageType.FILE, request_id=request_id)
            response.data = "start"
            if await self.send_response(client_id, response):
                for i in range(0, len(data), self.chunk_size):
                    await websocket.send_bytes(data[i:i + self.chunk_size])
                response.data = "end"
                await self.send_response(client_id, response)
            else:
                log.error(f"发送文件失败[{client_id}]: 标记符发送失败")
                return False
            return True
        except Exception as e:
            log.error(f"发送文件失败[{client_id}]: {str(e)}")
            return False

    async def _check_all_connections(self) -> None:
        while True:
            try:
                async with self.lock:
                    for client_id in list(self.active_connections):
                        if not await self._check_single_connection(client_id):
                            fails = self.check_failures[client_id] = self.check_failures.get(client_id, 0) + 1
                            if fails >= self.max_failures:
                                await self.disconnect(client_id)
                        else:
                            self.check_failures.pop(client_id, None)
            except Exception as e:
                log.error(f"连接检查错误: {str(e)}")
            finally:
                await asyncio.sleep(self.check_interval)

    async def _check_single_connection(self, client_id: str) -> bool:
        try:
            await self.send_response(client_id, WS_RESPONSE(
                type=WSMessageType.CHECK,
                data=int(time.time())
            ))
            return True
        except Exception:
            return False
