from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel

class WSMessageType(str, Enum):
    RESPONSE = "response"  # 普通响应
    FILE = "file"         # 文件传输
    CHECK = "check"       # 连接检查
    ERROR = "error"       # 错误响应

class WS_RESPONSE(BaseModel):
    type: WSMessageType = WSMessageType.RESPONSE
    code: int = 200
    from_api: Optional[str] = None
    nds_id: Optional[str] = None  
    message: Optional[str] = None
    data: Optional[Any] = None
    request_id: Optional[str] = None

class ScanRequest(BaseModel):
    id: str
    path: str
    filter: Optional[str] = None
