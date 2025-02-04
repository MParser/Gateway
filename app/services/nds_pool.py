import asyncio
from datetime import datetime
from app.core.logger import log
from typing import Dict, Optional
from dataclasses import dataclass
from app.core.nds_client import NDSClient
from contextlib import asynccontextmanager


class NDSError(Exception):
    """NDS错误"""
    def __init__(self, message: str, server_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.server_id = server_id
        nds_info = f"[NDS_ID:{server_id}] " if server_id else ""
        log.error(f"{nds_info}NDSPool Error: {message}")


@dataclass
class PoolConfig:
    """连接池配置"""
    protocol: str
    host: str
    port: int
    user: str
    passwd: str
    pool_size: int = 2


@dataclass
class ConnectionInfo:
    """连接信息"""
    client: Optional[NDSClient]


# noinspection PyBroadException
class NDSPool:
    """NDS连接池管理器"""

    def __init__(self):
        self._pools: Dict[str, asyncio.Queue[ConnectionInfo]] = {}  # server_id -> connection queue
        self._configs: Dict[str, PoolConfig] = {}  # server_id -> config
        self.nds_log = {}

    def add_server(self, server_id: str, config: PoolConfig) -> None:
        """添加服务器配置"""
        self._configs[server_id] = config
        self._pools[server_id] = asyncio.Queue(maxsize=config.pool_size)
        self.nds_log[server_id] = 0
        log.info(f"[NDS_ID:{server_id}] Server added to pool")

    @asynccontextmanager
    async def get_client(self, server_id: str):
        """获取客户端连接的上下文管理器
        
        Args:
            server_id: 服务器ID
        """
        if server_id not in self._configs:
            raise NDSError(f"Server {server_id} not configured", server_id)

        queue = self._pools[server_id]
        conn = None

        try:
            # 1. 尝试从队列获取连接
            try:
                conn = queue.get_nowait()
                if not conn.client or not await conn.client.check_connect():
                    await self._close_connection(conn, server_id)
                    conn = None
            except asyncio.QueueEmpty:
                conn = None
                pass
            
            # 2. 如果没有可用连接，创建新连接
            if not conn:
                if queue.qsize() < self._configs[server_id].pool_size:
                    config = self._configs[server_id]
                    client = NDSClient(
                        protocol=config.protocol,
                        host=config.host,
                        port=config.port,
                        user=config.user,
                        passwd=config.passwd,
                        nds_id=server_id
                    )
                    await client.connect()
                    conn = ConnectionInfo(client=client)
                else:
                    # 3. 如果队列已满，等待可用连接
                    conn = await queue.get()  # 无限等待直到有可用连接
                    if not conn.client or not await conn.client.check_connect():
                        await self._close_connection(conn, server_id)
                        raise NDSError("Failed to get valid connection", server_id)

            # 4. 返回连接
            client = conn.client
            yield client

            # 5. 检查连接状态并决定是否放回队列
            try:
                is_valid = await client.check_connect()
            except:
                is_valid = False
            
            if is_valid:
                try:
                    await queue.put(conn)
                except:
                    await self._close_connection(conn, server_id)
            else:
                await self._close_connection(conn, server_id)

        except Exception as e:
            if conn:
                await self._close_connection(conn, server_id)
            log.error(f"[NDS_ID:{server_id}] Error in get_client: {e}")
            raise NDSError(f"Failed to get client: {e}", server_id)

    @staticmethod
    async def _close_connection(conn: ConnectionInfo, server_id: str) -> None:
        """关闭连接"""
        if conn and conn.client:
            try:
                await conn.client.close_connect()
            except Exception as e:
                log.error(f"[NDS_ID:{server_id}] Error closing connection: {e}")
            finally:
                conn.client = None

    async def close(self) -> None:
        """关闭连接池"""
        # 先复制一份server_id列表，避免在迭代过程中修改字典
        server_ids = list(self._pools.keys())
        
        # 逐个移除服务器
        for server_id in server_ids:
            try:
                await self.remove_server(server_id)
            except Exception as e:
                log.error(f"[NDS_ID:{server_id}] Error closing pool: {e}")
        
        log.info("All connection pools closed")

    async def remove_server(self, server_id: str) -> None:
        """移除服务器配置"""
        if server_id not in self._configs:
            return

        # 关闭所有连接
        queue = self._pools[server_id]
        while not queue.empty():
            try:
                conn = queue.get_nowait()
                await self._close_connection(conn, server_id)
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                log.error(f"[NDS_ID:{server_id}] Error closing connection: {e}")

        # 移除配置
        del self._pools[server_id]
        del self._configs[server_id]
        del self.nds_log[server_id]
        log.info(f"[NDS_ID:{server_id}] Server removed from pool")

    async def get_pool_status(self, server_id: str) -> Dict:
        """获取指定服务器的连接池状态"""
        if server_id not in self._configs:
            raise NDSError(f"Server {server_id} not configured", server_id)

        queue = self._pools[server_id]
        config = self._configs[server_id]
        
        # # 检查连接状态
        # is_connected = False
        # try:
        #     async with self.get_client(server_id) as client:
        #         is_connected = await client.check_connect()
        # except Exception as e:
        #     log.error(f"[NDS_ID:{server_id}] Error checking connection: {e}")

        return {
            "server_id": server_id,
            "protocol": config.protocol,
            "host": config.host,
            "port": config.port,
            "max_connections": config.pool_size,
            "available": config.pool_size - queue.qsize(),
            "current_connections": queue.qsize(),
            # "connected": is_connected,
            "last_used": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
    async def get_all_pool_status(self) -> Dict:
        """获取所有连接池的状态"""
        result = {}
        for server_id in self._configs:
            try:
                result[server_id] = await self.get_pool_status(server_id)
            except Exception as e:
                log.error(f"[NDS_ID:{server_id}] Error getting pool status: {e}")
                result[server_id] = {
                    "server_id": server_id,
                    "error": str(e),
                    "connected": False
                }
        return result

    def get_server_ids(self) -> list:
        """获取所有已配置的服务器ID列表"""
        return list(self._configs.keys())
