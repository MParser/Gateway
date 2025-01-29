from fastapi import FastAPI, responses
from loguru import logger
from app.core.logger import log
from app.core.events import event_manager
from app.core.config import config
from app.core.http_client import HttpClient, HttpConfig
import json


server = HttpClient(
    f"{config.get('server.protocol')}://{config.get('server.host')}:{config.get('server.port')}/api/",
    config=HttpConfig(timeout=config.get("server.timeout", 3600))
)

@event_manager.on_startup
async def startup_event(app: FastAPI):
    """
    应用启动事件
    在应用启动时执行
    """
    #  注册Gateway节点
    try:
        # 发送注册请求
        response = await server.post("gateway/register", json={
            "id": config.get("app.id"),
            "port": config.get("app.port"),
        })
        if response.get("code") == 200:
            response = response.get("data")
            log.info(f"Gateway注册成功: {response.get("id")} - {response.get('name')}")
        else:
            log.error(f"Gateway注册失败: {json.dumps(response, ensure_ascii=False)}")
    except Exception as e:
        log.error(f"Gateway注册失败: {str(e)}")
        
    log.info("Event service started")
    return


@event_manager.on_shutdown
async def shutdown_event(app: FastAPI):
    """
    应用关闭事件
    在应用关闭时执行
    """
    # 注销网关 (更新状态为离线)
    try:
        response = await server.put(f"gateway/{config.get('app.id')}", json={
            "status": 0
        })
        if response.get("code") == 200:
            response = response.get("data")
            log.info(f"网关注销成功: {response.get('id')} - {response.get('name')}")
        else:
            log.error(f"网关注销失败: {json.dumps(response, ensure_ascii=False)}")
    except Exception as e:
        log.error(f"网关注销失败: {str(e)}")
    log.info("Event service stopped")
    return
