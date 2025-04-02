import time
import asyncio
from typing import Dict, List, Tuple
from fastapi import WebSocket
from app.core.logger import log
from app.api.deps import WS_RESPONSE, WSMessageType


# noinspection PyBroadException
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_locks: Dict[str, asyncio.Lock] = {}  # 每个连接一个锁
        self.manager_lock = asyncio.Lock()  # 管理锁，只用于连接的添加和删除
        self.chunk_size = 524288  # 512KB
        self.check_interval = 30
        self.check_failures: Dict[str, int] = {}
        self.max_failures = 3
        self._check_task = asyncio.create_task(self._check_all_connections())
        log.info("连接检查任务已启动")

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        async with self.manager_lock:  # 使用管理锁
            if client_id in self.active_connections:
                await self.disconnect(client_id)
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.connection_locks[client_id] = asyncio.Lock()  # 为新连接创建锁
            self.check_failures.pop(client_id, None)
            log.debug(f"客户端[{client_id}]连接成功")

    async def disconnect(self, client_id: str) -> None:
        """
        断开指定客户端的连接
        
        :param client_id: 客户端ID
        """
        try:
            async with self.manager_lock:  # 使用管理锁
                if websocket := self.active_connections.pop(client_id, None):
                    try:
                        # 检查连接是否已经关闭
                        if not websocket.client_state.DISCONNECTED:
                            await websocket.close()
                    except Exception as e:
                        log.warning(f"关闭WebSocket连接时出现异常[{client_id}]: {str(e)}")
                    finally:
                        self.connection_locks.pop(client_id, None)  # 移除连接锁
                        self.check_failures.pop(client_id, None)
                        log.debug(f"客户端[{client_id}]已断开")
        except Exception as e:
            log.error(f"断开连接过程中出现异常[{client_id}]: {str(e)}")

    async def send_response(self, client_id: str, response: WS_RESPONSE, *, lock_acquired: bool = False) -> bool:
        """
        发送WebSocket响应
        
        :param client_id: 客户端ID
        :param response: 响应对象，必须是 WS_RESPONSE 类型
        :param lock_acquired: 是否已经获取了锁，用于避免死锁
        :return: 发送是否成功
        """
        if not (websocket := self.active_connections.get(client_id)):
            return False
        
        if not (lock := self.connection_locks.get(client_id)):
            return False

        try:
            if lock_acquired:
                # 如果已经获取了锁，直接发送
                await websocket.send_json(response.model_dump())
                return True
            else:
                # 如果没有获取锁，需要先获取锁
                async with lock:
                    await websocket.send_json(response.model_dump())
                    return True
        except Exception as e:
            log.error(f"发送响应失败[{client_id}]: {str(e)}")
            return False

    async def send_file(self, client_id: str, data: bytes, request_id: str) -> bool:
        """
        发送文件数据
        
        :param client_id: 客户端ID
        :param data: 要发送的文件数据
        :param request_id: 请求ID
        :return: 发送是否成功
        """
        if not (websocket := self.active_connections.get(client_id)):
            return False
        
        if not (lock := self.connection_locks.get(client_id)):
            return False

        try:
            async with lock:
                response = WS_RESPONSE(type=WSMessageType.FILE, request_id=request_id)
                response.data = "start"
                # 传入lock_acquired=True，因为我们已经获取了锁
                if await self.send_response(client_id, response, lock_acquired=True):
                    for i in range(0, len(data), self.chunk_size):
                        await websocket.send_bytes(data[i:i + self.chunk_size])
                    response.data = "end"
                    await self.send_response(client_id, response, lock_acquired=True)
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
                # 获取所有客户端ID的快照，避免在检查过程中的并发修改
                async with self.manager_lock:
                    client_ids = list(self.active_connections.keys())
                
                # 并发检查所有连接
                check_tasks = []
                for client_id in client_ids:
                    check_tasks.append(self._check_single_connection(client_id))
                
                if check_tasks:
                    # 等待所有检查完成
                    results = await asyncio.gather(*check_tasks, return_exceptions=True)
                    
                    # 处理检查结果
                    async with self.manager_lock:
                        for client_id, result in zip(client_ids, results):
                            if isinstance(result, Exception):
                                fails = self.check_failures[client_id] = self.check_failures.get(client_id, 0) + 1
                                if fails >= self.max_failures:
                                    await self.disconnect(client_id)
                            elif not result:
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
