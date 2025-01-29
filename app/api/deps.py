from typing import Callable
from app.schemas.response import ResponseModel
from app.core.errors import *
import uuid
from functools import wraps

def generate_request_id() -> str:
    """生成请求ID"""
    return str(uuid.uuid4())

def response_wrapper(func: Callable) -> Callable:
    """
    错误处理装饰器
    用于统一处理API错误和响应
    
    示例:
    ```python
    @router.get("/users/{user_id}")
    @handle_errors
    async def get_user(user_id: int):
        if user_id not in users:
            raise NotFound(f"用户不存在: {user_id}")
        return users[user_id]  # 成功时直接返回数据
    ```
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            # 执行原函数
            result = await func(*args, **kwargs)
            
            # 如果返回的已经是ResponseModel，直接返回其字典形式
            if isinstance(result, ResponseModel):
                return result.model_dump()
            
            # 成功响应
            return {
                "code": 200,
                "msg": "success",
                "data": result,
                "request_id": generate_request_id()
            }
            
        except AppError as e:
            # 统一处理所有AppError及其子类异常
            return {
                "code": e.error_code,
                "msg": e.error_msg,
                "data": e.error_detail,
                "request_id": generate_request_id()
            }
        except Exception as e:
            # 处理其他异常
            return {
                "code": 500,
                "msg": str(e),
                "data": None,
                "request_id": generate_request_id()
            }
    
    return wrapper
