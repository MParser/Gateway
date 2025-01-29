import psutil
import platform
from typing import Dict
from datetime import datetime

class SystemInfo:
    """系统信息工具类"""
    
    @staticmethod
    def get_system_stats() -> Dict[str, str]:
        """
        获取系统状态信息
        
        返回:
            包含CPU、内存、磁盘等系统信息的字典
        """
        # CPU信息
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # 内存信息
        memory = psutil.virtual_memory()
        memory_total = memory.total / (1024 * 1024 * 1024)  # 转换为GB
        memory_used = memory.used / (1024 * 1024 * 1024)    # 转换为GB
        memory_percent = memory.percent
        
        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_total = disk.total / (1024 * 1024 * 1024)      # 转换为GB
        disk_used = disk.used / (1024 * 1024 * 1024)        # 转换为GB
        disk_percent = disk.percent
        
        # 系统启动时间
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        return {
            "status": "healthy",
            "system": platform.system(),
            "python_version": platform.python_version(),
            "cpu": {
                "usage_percent": f"{cpu_percent:.1f}%",
                "core_count": str(cpu_count)
            },
            "memory": {
                "total": f"{memory_total:.1f}GB",
                "used": f"{memory_used:.1f}GB",
                "usage_percent": f"{memory_percent:.1f}%"
            },
            "disk": {
                "total": f"{disk_total:.1f}GB",
                "used": f"{disk_used:.1f}GB",
                "usage_percent": f"{disk_percent:.1f}%"
            },
            "uptime": {
                "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S"),
                "uptime_days": f"{uptime.days}天 {uptime.seconds//3600}小时"
            }
        }
