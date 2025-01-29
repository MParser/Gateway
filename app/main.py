from fastapi import FastAPI
from app.core.logger import log
from app.core.events import event_manager


@event_manager.on_startup
async def startup_event(app: FastAPI):
    """
    应用启动事件
    在应用启动时执行
    """
   
    
    log.info("Event service started")
    return


@event_manager.on_shutdown
async def shutdown_event(app: FastAPI):
    """
    应用关闭事件
    在应用关闭时执行
    """
    log.info("Event service stopped")
    return