from fastapi import FastAPI
from app.core.logger import log
from app.core.events import event_manager
from app.utils.server import GatewayServer

server = GatewayServer()


# noinspection PyUnusedLocal
@event_manager.on_startup
async def startup_event(app: FastAPI):
    """
    应用启动事件
    在应用启动时执行
    """
    #  注册Gateway节点
    try:
        # 发送注册请求
        log.info("正在注册网关节点...")
        response = await server.register()
        log.info(f"Gateway注册成功: {response.get('id')} - {response.get('name')}")
    except Exception as e:
        log.error(f"Gateway注册失败: {str(e)}")
    log.info("Event service started")
    return

# noinspection PyUnusedLocal
@event_manager.on_shutdown
async def shutdown_event(app: FastAPI):
    """
    应用关闭事件
    在应用关闭时执行
    """
    # 注销网关 (更新状态为离线)
    try:
        await server.unregister()
        log.info("网关注销成功")
    except Exception as e:
        log.error(f"Gateway注销失败: {str(e)}")
    log.info("Event service stopped")
    return
