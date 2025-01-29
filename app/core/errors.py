from typing import Any, Optional

class AppError(Exception):
    """
    应用异常基类
    
    属性:
        error_code: 错误码
        error_msg: 错误信息
        error_detail: 错误详情
    """
    def __init__(
        self,
        error_code: int,
        error_msg: str,
        error_detail: Optional[Any] = None
    ):
        self.error_code = error_code
        self.error_msg = error_msg
        self.error_detail = error_detail
        super().__init__(self.error_msg)

class ValidationError(AppError):
    """参数验证错误"""
    def __init__(self, msg: str = "参数验证错误", detail: Any = None):
        super().__init__(
            error_code=400,
            error_msg=msg,
            error_detail=detail
        )

class AuthenticationError(AppError):
    """认证错误"""
    def __init__(self, msg: str = "认证失败", detail: Any = None):
        super().__init__(
            error_code=401,
            error_msg=msg,
            error_detail=detail
        )


# noinspection PyShadowingBuiltins
class PermissionError(AppError):
    """权限错误"""
    def __init__(self, msg: str = "权限不足", detail: Any = None):
        super().__init__(
            error_code=403,
            error_msg=msg,
            error_detail=detail
        )

class NotFoundError(AppError):
    """资源不存在错误"""
    def __init__(self, msg: str = "资源不存在", detail: Any = None):
        super().__init__(
            error_code=404,
            error_msg=msg,
            error_detail=detail
        )

class BusinessError(AppError):
    """业务逻辑错误"""
    def __init__(self, msg: str, code: int = 500, detail: Any = None):
        super().__init__(
            error_code=code,
            error_msg=msg,
            error_detail=detail
        )
