import uuid
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional, Dict, Any


# 定义泛型类型变量
DataT = TypeVar("DataT")

class ResponseModel(BaseModel, Generic[DataT]):
    """
    统一响应模型
    
    所有API响应都会被包装成这个格式，包括：
    - 成功响应：code=200，返回实际数据
    - 业务错误：code=400系列，返回错误信息
    - 系统错误：code=500系列，返回错误详情
    
    示例：
    ```json
    {
        "code": 200,
        "message": "success",
        "data": { ... },
        "request_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    """
    code: int = Field(
        default=200,
        description="响应状态码",
        examples=[200, 400, 401, 403, 404, 500],
        title="状态码"
    )
    message: str = Field(
        default="success",
        description="响应消息",
        examples=["success", "参数错误", "未授权", "权限不足", "资源不存在", "服务器错误"],
        title="消息"
    )
    data: Optional[DataT] = Field(
        default=None,
        description="响应数据",
        title="数据"
    )
    request_id: Optional[str] = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="请求ID，用于追踪和调试",
        title="请求ID",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    
    class Config:
        """Pydantic配置类"""
        json_schema_extra = {
            "examples": [{
                "summary": "成功响应示例",
                "description": "这是一个成功的响应示例",
                "value": {
                    "code": 200,
                    "message": "success",
                    "data": {
                        "id": 1,
                        "name": "示例数据"
                    },
                    "request_id": "550e8400-e29b-41d4-a716-446655440000"
                }
            }]
        }
        

# 预定义常用响应类型
ResponseDict = ResponseModel[Dict[str, Any]]
ResponseString = ResponseModel[str]
ResponseInt = ResponseModel[int]
ResponseBool = ResponseModel[bool]
ResponseNone = ResponseModel[None]

# 类型名称
ResponseDict.model_name_handler = lambda: "字典响应模型"
ResponseString.model_name_handler = lambda: "字符串响应模型"
ResponseInt.model_name_handler = lambda: "整数响应模型"
ResponseBool.model_name_handler = lambda: "布尔响应模型"
ResponseNone.model_name_handler = lambda: "空响应模型"
