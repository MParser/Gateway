from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
from app.core.logger import log
from app.api.deps import response_wrapper
from app.api.v1.models.ws_models import WS_RESPONSE, WSMessageType
from app.api.v1.controllers.gateway_controller import GatewayController, ws_manage

# API路由
api_router = APIRouter(tags=["Gateway API"])

# 控制接口
@api_router.get("/control/start")
@response_wrapper
async def start():
    return await GatewayController.start()

@api_router.get("/control/stop")
@response_wrapper
async def stop():
    return await GatewayController.stop()

@api_router.get("/control/status")
@response_wrapper
async def status():
    return await GatewayController.status()

@api_router.get("/control/restart")
@response_wrapper
async def restart():
    return await GatewayController.restart()

# WebSocket入口
@api_router.websocket("/nds/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket连接处理"""
    try:
        await ws_manage.connect(websocket, client_id)
        
        while True:
            try:
                # 接收消息
                message = await websocket.receive_json()
                log.debug(f"收到消息[{client_id}]: {message}")
                
                # 处理消息
                try:
                    response = await GatewayController.handle_websocket_message(client_id, message)
                    if not isinstance(response, WS_RESPONSE):
                        log.error(f"无效的响应对象[{client_id}]: {response}")
                        response = WS_RESPONSE(
                            type=WSMessageType.ERROR,
                            code=500,
                            message="服务器内部错误：无效的响应对象"
                        )
                    await ws_manage.send_response(client_id, response)
                except Exception as e:
                    log.error(f"处理消息失败[{client_id}]: {str(e)}")
                    await ws_manage.send_response(client_id, WS_RESPONSE(
                        type=WSMessageType.ERROR,
                        code=500,
                        message=f"处理消息失败: {str(e)}"
                    ))
                
            except json.JSONDecodeError:
                await ws_manage.send_response(client_id, WS_RESPONSE(
                    type=WSMessageType.ERROR,
                    code=400,
                    message="无效的JSON格式"
                ))
                
    except WebSocketDisconnect:
        log.info(f"客户端断开连接[{client_id}]")
    except Exception as e:
        log.error(f"WebSocket错误[{client_id}]: {str(e)}")
    finally:
        await ws_manage.disconnect(client_id)
