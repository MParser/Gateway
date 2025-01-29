from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, Field
import uuid

# 定义泛型类型变量
DataT = TypeVar("DataT")

class ResponseModel(BaseModel, Generic[DataT]):
    """
    统一响应模型
    """
    code: int = Field(
        default=0,
        description="响应状态码，0表示成功，其他表示错误",
        examples=[0, 400, 401, 403, 404, 500]
    )
    msg: str = Field(
        default="success",
        description="响应信息",
        examples=["success", "参数错误", "未授权", "权限不足", "资源不存在", "服务器错误"]
    )
    data: Optional[DataT] = Field(
        default=None,
        description="响应数据，成功时返回具体数据，错误时可能包含错误详情"
    )
    request_id: Optional[str] = Field(
        default=str(uuid.uuid4()),
        description="请求ID，用于追踪和调试"
    )
    
    class Config:
        """Pydantic配置类"""
        json_schema_extra = {
            "examples": [
                {
                    "summary": "成功响应示例",
                    "description": "这是一个成功的响应示例",
                    "value": {
                        "code": 0,
                        "msg": "success",
                        "data": {
                            "id": 1,
                            "name": "示例数据"
                        },
                        "request_id": "550e8400-e29b-41d4-a716-446655440000"
                    }
                },
                {
                    "summary": "错误响应示例",
                    "description": "这是一个错误的响应示例",
                    "value": {
                        "code": 400,
                        "msg": "参数验证错误",
                        "data": {
                            "field": "username",
                            "error": "字段不能为空"
                        },
                        "request_id": "550e8400-e29b-41d4-a716-446655440001"
                    }
                }
            ]
        }
