from app.core.logger import log
from typing import Dict, Optional, Any
from app.utils.server import GatewayServer
from app.api.deps import WS_RESPONSE, WSMessageType
from app.services.ws_manager import ConnectionManager
from app.services.nds_pool import NDSPool, PoolConfig


# 全局实例
nds_pool = NDSPool()
server = GatewayServer()
ws_manage = ConnectionManager()


async def start():
    """启动NDS服务"""
    try:
        nds_arr = await server.nds_list()
        log.info(f"获取到{len(nds_arr)}个NDS")
        if not nds_arr:
            raise ValueError("NDS列表为空")

        for info in nds_arr:
            if nds := info.get("nds"):
                config = PoolConfig(
                    protocol=nds.get("Protocol"),
                    host=nds.get("Address"),
                    port=nds.get("Port"),
                    user=nds.get("Account"),
                    passwd=nds.get("Password"),
                    pool_size=nds.get("PoolSize"),
                )
                nds_id = str(nds.get("id"))
                nds_pool.add_server(nds_id, config)
        return "启动完成"
    except Exception as e:
        log.error(f"启动失败: {str(e)}")
        raise ValueError(f"启动失败: {str(e)}")


async def stop():
    """停止NDS服务"""
    await nds_pool.close()
    return "关闭完成"


async def status():
    """获取NDS状态"""
    return await nds_pool.get_all_pool_status()


async def restart():
    """重启NDS服务"""
    await stop()
    return await start()


async def handle_scan(nds_id: str, path: str, filter_pattern: Optional[str], response: WS_RESPONSE) -> None:
    """处理扫描请求"""
    if not nds_id or not path:
        raise ValueError("缺少必要参数: nds_id 或 path")

    try:
        nds_id = str(nds_id)  # 确保 nds_id 是字符串类型
        async with nds_pool.get_client(nds_id) as client:
            response.data = await client.scan(path, filter_pattern)
            response.message = "扫描成功"
    except Exception as e:
        response.code = 500
        response.message = str(e)
        response.type = WSMessageType.ERROR


async def handle_read(nds_id: str, path: str, header_offset: int, size: int,
                      client_id: str, response: WS_RESPONSE) -> None:
    """处理读取请求"""
    if not all([nds_id, path, isinstance(header_offset, int), isinstance(size, int), size > 0]):
        raise ValueError("缺少必要参数或参数类型错误")

    try:
        nds_id = str(nds_id)  # 确保 nds_id 是字符串类型
        log.info(f"read file{path} header_offset: {header_offset}, size:{size}")
        async with nds_pool.get_client(nds_id) as client:
            log.info("Get NDS")
            if data := await client.read_file_bytes(path, header_offset, size):
                log.info("Get Data")
                if await ws_manage.send_file(client_id, data, response.request_id):
                    response.message = "success"
                    response.data = {
                        "nds_id": nds_id,
                        "path": path,
                        "header_offset": header_offset,
                        "size": size
                    }
                    response.code = 200
                else:
                    response.message = "failed"
                    response.code = 500
            else:
                raise ValueError("读取文件失败")
    except Exception as e:
        response.code = 500
        response.message = str(e)
        response.type = WSMessageType.ERROR


async def handle_zip_info(nds_id: str, path: str, response: WS_RESPONSE) -> None:
    """处理ZIP信息请求"""
    if not nds_id or not path:
        raise ValueError("缺少必要参数: nds_id 或 path")

    try:
        nds_id = str(nds_id)  # 确保 nds_id 是字符串类型
        async with nds_pool.get_client(nds_id) as client:
            data = await client.get_zip_info(path)
            # KeyType 继承自 dict，直接使用 dict() 转换
            serializable_data = [dict(item) for item in data]
            response.data = serializable_data
            response.message = "success"
    except Exception as e:
        response.code = 500
        response.message = str(e)
        response.type = WSMessageType.ERROR


async def handle_websocket_message(client_id: str, message: Dict[str, Any]) -> WS_RESPONSE:
    """处理WebSocket消息"""
    # 验证请求
    if not all(k in message for k in ["api", "request_id"]):
        raise ValueError("缺少必要字段")

    api, request_id = message["api"], message["request_id"]
    params = message.get("params", {})

    # 创建响应对象
    response = WS_RESPONSE(from_api=api, request_id=request_id)
    if nds_id := params.get("nds_id"):
        response.nds_id = str(nds_id)  # 确保 nds_id 是字符串类型

    # 处理请求
    handlers = {
        "scan": lambda: handle_scan(
            nds_id=params.get("nds_id"),
            path=params.get("path"),
            filter_pattern=params.get("filter"),
            response=response
        ),
        "read": lambda: handle_read(
            nds_id=params.get("nds_id"),
            path=params.get("path"),
            header_offset=params.get("header_offset", 0),
            size=params.get("size", 0),
            client_id=client_id,
            response=response
        ),
        "zip_info": lambda: handle_zip_info(
            nds_id=params.get("nds_id"),
            path=params.get("path"),
            response=response
        ),
    }

    try:
        if handler := handlers.get(api):
            await handler()
        else:
            response.type = WSMessageType.ERROR
            response.code = 404
            response.message = f"未知的API: {api}"
    except ValueError as e:
        response.type = WSMessageType.ERROR
        response.code = 400
        response.message = str(e)
    except Exception as e:
        log.error(f"处理请求出错[{client_id}]: {str(e)}")
        response.type = WSMessageType.ERROR
        response.code = 500
        response.message = "服务器内部错误"
        response.data = str(e)

    return response