import os
import json
from pathlib import Path
from typing import Dict, Any
from collections import deque
import asyncio
from datetime import datetime
from fastapi import HTTPException
from app.core.config import config
from fastapi.responses import FileResponse
from starlette.websockets import WebSocketState
from app.core.logger import logger, get_log_files
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

api_router = APIRouter(prefix="/logs", tags=["日志接口"])  # 移除默认前缀

# 存储最近1000条日志
log_queue = deque(maxlen=1000)
# 活跃的WebSocket连接集合
active_connections = []
# 添加锁来保护共享资源
connection_lock = asyncio.Lock()
# 添加锁来保护日志队列
log_queue_lock = asyncio.Lock()
static_dir = Path(__file__).parent.parent / "static"
def format_file_size(size_in_bytes):
    """格式化文件大小
    
    Args:
        size_in_bytes: 文件大小（字节）
    
    Returns:
        str: 格式化后的文件大小
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} TB"

@api_router.get("/", include_in_schema=False)
async def get_logs_page():
    """返回日志查看页面"""
    
    return FileResponse(static_dir / "logs/index.html")

@api_router.get("/style.css", include_in_schema=False)
async def get_logs_style():
    """返回日志页面的样式文件"""
    return FileResponse(static_dir / "logs/style.css", media_type="text/css")

@api_router.get("/script.js", include_in_schema=False)
async def get_logs_script():
    """返回日志页面的脚本文件"""
    return FileResponse(static_dir / "logs/script.js", media_type="application/javascript")

@api_router.get("/config", include_in_schema=False)
async def get_logs_config():
    """获取日志配置信息"""
    return {
        "title": f"{config.get('app.name', '')} Logs"  # 使用config获取标题，默认值为"Log Viewer"
    }

@api_router.get("/files", include_in_schema=False)
async def get_log_files_list():
    """获取所有日志文件列表"""
    files = get_log_files()
    return [{
        "ctime": datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "filename": path.name,
        "size": format_file_size(path.stat().st_size)
    } for path, ctime in files if path.stat().st_size > 0]

@api_router.get("/content/{filename}", include_in_schema=False)
async def get_log_content(
    filename: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=1000, description="每页数量")
):
    """获取指定日志文件的内容，支持分页
    
    Args:
        filename: 日志文件名
        page: 页码，从1开始
        page_size: 每页显示的日志条数
    """
    try:
        # 获取日志目录
        log_files = get_log_files()
        if not log_files:
            raise HTTPException(status_code=404, detail="没有找到日志目录")
        
        log_dir = log_files[0][0].parent
        
        # 构建日志文件路径
        log_file = log_dir / filename
        if not os.path.exists(log_file):
            raise HTTPException(status_code=404, detail=f"日志文件 {filename} 不存在")

        # 读取日志文件内容
        with open(log_file, 'r', encoding='utf-8') as f:
            all_logs = f.readlines()

        # 计算总页数和分页数据
        total_logs = len(all_logs)
        total_pages = (total_logs + page_size - 1) // page_size  # 向上取整
        
        # 确保页码在有效范围内
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
            
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_logs)
        
        # 确保日志内容是有效的JSON格式
        logs = []
        for log in all_logs[start_idx:end_idx]:
            try:
                # 尝试解析JSON
                log_obj = json.loads(log)
                logs.append(json.dumps(log_obj, ensure_ascii=False))
            except json.JSONDecodeError:
                # 如果不是JSON格式，直接添加原始文本
                logs.append(log.strip())
        
        # 返回分页后的日志内容
        return {
            "logs": logs,
            "total": total_logs,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": page_size
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取日志文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"读取日志文件失败: {str(e)}")

# noinspection PyBroadException
@api_router.websocket("/ws")
async def websocket_logs(websocket: WebSocket):
    """处理WebSocket连接，用于实时推送日志"""
    await websocket.accept()
    
    # 使用锁保护添加连接的操作
    async with connection_lock:
        active_connections.append(websocket)
    
    try:
        # 发送现有的日志队列 - 使用锁保护读取操作
        async with log_queue_lock:
            # 创建日志队列的副本进行迭代
            logs_to_send = list(log_queue)
            
        # 在锁外发送日志
        for log in logs_to_send:
            try:
                await websocket.send_json(log)
            except Exception:
                break
                
        # 等待心跳消息
        while True:
            data = await websocket.receive_text()
            if data == "heartbeat":
                await websocket.send_text("heartbeat")
    except WebSocketDisconnect:
        # 安全地移除连接
        async with connection_lock:
            if websocket in active_connections:
                active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {str(e)}")
        async with connection_lock:
            if websocket in active_connections:
                active_connections.remove(websocket)


# noinspection PyBroadException
async def broadcast_log(log: Dict[str, Any]):
    """广播日志消息到所有连接的客户端
    
    Args:
        log: 日志消息字典，包含level和message等信息
    """
    # 将日志添加到队列 - 使用锁保护写入操作
    async with log_queue_lock:
        log_queue.append(log)
    
    # 创建一个连接列表的副本，避免在迭代过程中修改原列表
    async with connection_lock:
        connections = list(active_connections)
    
    # 广播到所有连接的客户端
    for connection in connections:
        try:
            if connection.client_state == WebSocketState.CONNECTED:
                await connection.send_json(log)
        except Exception:
            try:
                await connection.close()
            except:
                pass
            # 安全地移除连接
            async with connection_lock:
                if connection in active_connections:
                    active_connections.remove(connection)
