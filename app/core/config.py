import os
import json
from pathlib import Path
from typing import Dict, Any


# noinspection PyMethodMayBeStatic,PyTypeChecker
class _ConfigManager:
    """
    通用配置管理器
    支持从环境变量、.env文件和config.json动态加载配置
    
    环境变量和.env文件的命名约定：
    - 使用下划线连接节点和配置项
    - 例如：APP_HOST 对应 {"app": {"host": value}}
    - 例如：LOG_FILE_PATH 对应 {"log": {"file": {"path": value}}}
    """
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._json_config: Dict[str, Any] = {}
        self._env_file_config: Dict[str, Any] = {}
        self._env_vars_config: Dict[str, Any] = {}
        self._load_config()

    def _convert_value(self, value: str) -> Any:
        """
        增强的类型转换功能
        支持：整数、浮点数、布尔值、None值的转换
        """
        if not isinstance(value, str):
            return value
            
        # 处理None值
        if value.lower() in ('none', 'null'):
            return None
            
        # 处理布尔值
        if value.lower() in ('true', 'yes', 'on', '1'):
            return True
        if value.lower() in ('false', 'no', 'off', '0'):
            return False
            
        # 处理数字
        try:
            if value.isdigit():
                return int(value)
            if value.replace(".", "", 1).isdigit():
                return float(value)
        except (ValueError, AttributeError):
            pass
            
        # 保持原始字符串
        return value

    def _load_json_config(self) -> Dict[str, Any]:
        """加载JSON配置文件"""
        config_path = Path("config.json")
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_json_config(self):
        """保存配置到JSON文件"""
        config_path = Path("config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self._json_config, f, indent=4, ensure_ascii=False)

    def _save_env_file(self):
        """保存配置到.env文件"""
        env_path = Path(".env")
        env_lines = []
        
        def _flatten_dict(d: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
            """将嵌套字典扁平化为环境变量格式"""
            items = []
            for k, v in d.items():
                new_key = f"{prefix}_{k}" if prefix else k
                if isinstance(v, dict):
                    items.extend(_flatten_dict(v, new_key).items())
                else:
                    items.append((new_key.upper(), str(v)))
            return dict(items)
        
        # 转换为环境变量格式
        flat_config = _flatten_dict(self._env_file_config)
        
        # 保持现有的注释和格式
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and line.strip().startswith("#"):
                        env_lines.append(line.rstrip())
        
        # 添加配置项
        for key, value in sorted(flat_config.items()):
            env_lines.append(f"{key}={value}")
        
        # 写入文件
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(env_lines) + "\n")

    def _convert_to_env_key(self, key: str) -> str:
        """将点号分隔的键转换为环境变量格式"""
        return key.replace(".", "_").upper()

    def _create_nested_dict(self, key: str, value: Any) -> Dict[str, Any]:
        """创建嵌套字典结构"""
        result = {}
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        return result

    def set(self, key: str, value: Any, save: bool = True):
        """
        设置配置值
        
        :param key: 配置键，使用点号分隔的路径
        :param value: 配置值
        :param save: 是否立即保存到文件
        """
        # 创建嵌套字典结构
        nested_config = self._create_nested_dict(key, value)
        
        if self.config_override:
            # 当CONFIG_OVERRIDE为true时，只修改config.json
            self._json_config = self._merge_configs(self._json_config, nested_config)
            if save:
                self._save_json_config()
        else:
            # 当CONFIG_OVERRIDE为false时，修改所有配置源
            # 1. 修改环境变量
            env_key = self._convert_to_env_key(key)
            os.environ[env_key] = str(value)
            self._env_vars_config = self._merge_configs(
                self._env_vars_config, nested_config
            )
            
            # 2. 修改.env文件
            self._env_file_config = self._merge_configs(
                self._env_file_config, nested_config
            )
            
            # 3. 修改config.json
            self._json_config = self._merge_configs(self._json_config, nested_config)
            
            if save:
                self._save_json_config()
                self._save_env_file()

    def _parse_env_key(self, key: str, value: str) -> Dict[str, Any]:
        """将环境变量键值对转换为嵌套字典"""
        parts = key.lower().split('_')
        
        # 使用增强的类型转换
        converted_value = self._convert_value(value)

        result = {}
        current = result
        for _, part in enumerate(parts[:-1]):
            current[part] = {}
            current = current[part]
        current[parts[-1]] = converted_value
        
        return result

    def _load_env_file(self) -> Dict[str, Any]:
        """加载.env文件"""
        env_path = Path(".env")
        if not env_path.exists():
            return {}
            
        env_config = {}
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        key, value = line.split("=", 1)
                        nested_config = self._parse_env_key(key.strip(), value.strip())
                        env_config = self._merge_configs(env_config, nested_config)
                    except ValueError:
                        continue  # 跳过格式不正确的行
        return env_config

    def _load_env_vars(self) -> Dict[str, Any]:
        """加载环境变量"""
        env_config = {}
        for key, value in os.environ.items():
            nested_config = self._parse_env_key(key, value)
            env_config = self._merge_configs(env_config, nested_config)
        return env_config

    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并配置字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def _load_config(self):
        """加载所有配置并按优先级合并"""
        self._json_config = self._load_json_config()
        self._env_file_config = self._load_env_file()
        self._env_vars_config = self._load_env_vars()
        
        self.config_override = self._json_config.get("CONFIG_OVERRIDE", False)
        
        if self.config_override:
            # JSON配置优先级最高
            self._config = self._merge_configs(self._env_file_config, self._env_vars_config)
            self._config = self._merge_configs(self._config, self._json_config)
        else:
            # 环境变量优先级最高
            self._config = self._merge_configs(self._json_config, self._env_file_config)
            self._config = self._merge_configs(self._config, self._env_vars_config)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持使用点号访问嵌套配置"""
        if not key:
            return default
            
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

    def reload(self):
        """重新加载配置"""
        self._load_config()

# 创建全局配置实例
config = _ConfigManager()

# 只导出config实例
__all__ = ['config']
