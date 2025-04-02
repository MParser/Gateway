import json
from app.core.logger import log
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.deps import response_wrapper, WS_RESPONSE, WSMessageType
from app.core.gateway import start, stop, status, restart, handle_websocket_message, ws_manage

# API router
api_router = APIRouter(tags=["Gateway API"])

# Control endpoints
@api_router.get("/control/start", summary="启动网关服务")
@response_wrapper
async def start_service():
    return await start()

@api_router.get("/control/stop", summary="停止网关服务")
@response_wrapper
async def stop_service():
    return await stop()

@api_router.get("/control/status", summary="获取网关状态")
@response_wrapper
async def status_service():
    return await status()

@api_router.get("/control/restart", summary="重启网关服务")
@response_wrapper
async def restart_service():
    return await restart()

# WebSocket endpoint
@api_router.websocket("/nds/ws/{client_id}")
async def nds_control(websocket: WebSocket, client_id: str):
    """WebSocket connection handler"""
    try:
        await ws_manage.connect(websocket, client_id)

        while True:
            try:
                # Receive message
                message = await websocket.receive_json()
                log.debug(f"Received message[{client_id}]: {message}")

                # Handle message
                try:
                    # 检查是否为check，如果是则跳过，无需返回任何信息
                    if message.get("api", "") == "check_connection":
                        continue

                    response = await handle_websocket_message(client_id, message)
                    if not isinstance(response, WS_RESPONSE):
                        log.error(f"Invalid response object[{client_id}]: {response}")
                        response = WS_RESPONSE(
                            type=WSMessageType.ERROR,
                            code=500,
                            message="Internal server error: Invalid response object"
                        )
                    await ws_manage.send_response(client_id, response)
                except Exception as e:
                    log.error(f"Failed to handle message[{client_id}]: {str(e)}")
                    await ws_manage.send_response(client_id, WS_RESPONSE(
                        type=WSMessageType.ERROR,
                        code=500,
                        message=f"Failed to handle message: {str(e)}"
                    ))

            except json.JSONDecodeError:
                await ws_manage.send_response(client_id, WS_RESPONSE(
                    type=WSMessageType.ERROR,
                    code=400,
                    message="Invalid JSON format"
                ))

    except WebSocketDisconnect:
        log.info(f"Client disconnected[{client_id}]")
    except Exception as e:
        log.error(f"WebSocket error[{client_id}]: {str(e)}")
    finally:
        await ws_manage.disconnect(client_id)
