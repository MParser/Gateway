import sys
import logging
from pathlib import Path
from loguru import logger
import asyncio
from app.core.config import config

# 移除默认处理器
logger.remove()

# 日志格式
log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# 添加控制台处理器
if config.get("log.console", True):
    logger.add(
        sys.stdout, 
        format=log_format,
        level=config.get("log.level", "INFO").upper(),  
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

# 确保日志目录存在
log_path = Path(config.get("log.file.path", "logs/app.log")).parent
log_path.mkdir(exist_ok=True)

# 添加文件日志处理器
logger.add(
    config.get("log.file.path", "logs/app_{time}.log"),
    rotation=config.get("log.file.max_size", "10MB"),     # 按文件大小切割
    retention=int(config.get("log.file.backup_count", 5)),     # 保留文件数量
    level=config.get("log.level", "INFO").upper(),               # 从配置文件获取日志级别
    format=log_format,                                    # 使用默认格式
    encoding="utf-8",
    enqueue=True,             # 启用队列模式，适合多进程
    compression="zip",        # 压缩日志
)

async def websocket_handler(message):
    """处理日志并通过WebSocket广播"""
    # 构建与控制台相同格式的日志
    log_entry = {
        'time': message.record['time'].strftime('%Y-%m-%d %H:%mm:%S.%f')[:-3],
        'level': message.record['level'].name,
        'name': message.record.get('name', ''),
        'function': message.record.get('function', ''),
        'line': message.record.get('line', ''),
        'message': message.record['message'],
        'formatted': f"{message.record['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} | "
                    f"{message.record['level'].name:<8} | "
                    f"{message.record.get('name', '')}:{message.record.get('function', '')}:{message.record.get('line', '')} | "
                    f"{message.record['message']}"
    }
    # 导入broadcast_log函数
    from app.api.logs import broadcast_log
    await broadcast_log(log_entry)

def sync_websocket_handler(message):
    """同步环境下的WebSocket处理器"""
    loop = asyncio.get_event_loop()
    loop.create_task(websocket_handler(message))

# 添加WebSocket日志处理器
logger.add(sync_websocket_handler, level="INFO")

# 配置标准库日志处理器
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # 尝试从record中获取正确的模块名和函数名
        module = record.name
        function = record.funcName if hasattr(record, 'funcName') else ''
        line = record.lineno if hasattr(record, 'lineno') else 0

        # 转换日志级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 使用opt()来保持调用信息
        logger.opt(depth=6, exception=record.exc_info).bind(
            name=module,
            function=function,
            line=line
        ).log(level, record.getMessage())

# 配置所有Python标准库日志
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

# 特别配置uvicorn和fastapi的日志
for _log in ['uvicorn', 'uvicorn.access', 'uvicorn.error', 'fastapi']:
    _logger = logging.getLogger(_log)
    _logger.handlers = [InterceptHandler()]
    _logger.propagate = False

# 设置未捕获异常的处理器
def handle_exception(exc_type, exc_value, exc_traceback):
    """处理未捕获的异常"""
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).error("未捕获的异常")

# 设置异步异常处理器
def handle_asyncio_exception(_, context):
    """处理异步代码中的异常"""
    exception = context.get("exception")
    if exception:
        logger.opt(exception=exception).error("异步代码中的未捕获异常")
    else:
        logger.error(f"异步异常: {context['message']}")

# 设置异常处理器
sys.excepthook = handle_exception
asyncio.get_event_loop().set_exception_handler(handle_asyncio_exception)

# 导出日志对象
log = logger

def get_log_files():
    """获取所有日志文件
    
    Returns:
        list: [(文件路径, 文件创建时间)]列表，按时间排序
    """
    log_files = []
    log_dir = Path(config.get("log.file.path", "logs/")).parent
    
    # 获取所有.log和.zip文件
    for file in log_dir.glob("*.log"):
        log_files.append((file, file.stat().st_ctime))
    for file in log_dir.glob("*.log.zip"):
        log_files.append((file, file.stat().st_ctime))
    
    # 按创建时间排序
    return sorted(log_files, key=lambda x: x[1], reverse=True)

def read_log_file(file_path: Path, page: int = 1, page_size: int = 100):
    """读取日志文件内容
    
    Args:
        file_path: 日志文件路径
        page: 页码，从1开始
        page_size: 每页显示的日志条数
        
    Returns:
        tuple: (总页数, 当前页日志列表)
    """
    import zipfile
    import io
    
    # 如果是zip文件，先解压
    if file_path.suffix == '.zip':
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            # 获取zip中的日志文件名
            log_name = next((name for name in zip_ref.namelist() if name.endswith('.log')), None)
            if not log_name:
                return 0, []
            # 读取日志内容
            with zip_ref.open(log_name) as f:
                content = io.TextIOWrapper(f, encoding='utf-8').readlines()
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
    
    # 计算总页数
    total_pages = (len(content) + page_size - 1) // page_size
    
    # 获取当前页的日志
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    current_page_logs = content[start_idx:end_idx]
    
    return total_pages, current_page_logs
