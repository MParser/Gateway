from typing import Callable, List
from fastapi import FastAPI
import logging
import importlib

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventManager:
    """事件管理器，用于管理应用的启动和关闭事件"""
    
    def __init__(self):
        self.startup_handlers: List[Callable] = []
        self.shutdown_handlers: List[Callable] = []
        self._handlers_loaded = False
        self._entry_point = "app.main"  # 默认入口点模块
    
    def set_entry_point(self, module_name: str):
        """
        设置应用入口点模块
        """
        self._entry_point = module_name
    
    def on_startup(self, func: Callable) -> Callable:
        """
        启动事件装饰器
        用于注册应用启动时需要执行的函数
        """
        self.startup_handlers.append(func)
        return func
    
    def on_shutdown(self, func: Callable) -> Callable:
        """
        关闭事件装饰器
        用于注册应用关闭时需要执行的函数
        """
        self.shutdown_handlers.append(func)
        return func
    
    def discover_handlers(self):
        """
        自动发现并加载所有的事件处理函数
        通过导入入口点模块来加载事件处理函数
        """
        if self._handlers_loaded:
            return
            
        try:
            # 导入入口点模块
            importlib.import_module(self._entry_point)
            self._handlers_loaded = True
            
        except Exception as e:
            logger.error(f"加载入口点模块时出错: {str(e)}")
    
    async def run_startup(self, app: FastAPI):
        """执行所有启动事件"""
        self.discover_handlers()
        
        if not self.startup_handlers:
            return
            
        for handler in self.startup_handlers:
            await handler(app)
    
    async def run_shutdown(self, app: FastAPI):
        """执行所有关闭事件"""
        if not self.shutdown_handlers:
            return
            
        for handler in self.shutdown_handlers:
            await handler(app)

# 创建全局事件管理器实例
event_manager = EventManager()
