import httpx
from dataclasses import dataclass
from app.core.logger import logger
from typing import Optional, Dict, Any, Union

@dataclass
class HttpConfig:
    """HTTP客户端配置"""
    timeout: int = 3600  # 默认超时时间1小时

class HttpClient:
    """HTTP客户端封装"""
    def __init__(self, base_url: str, config: Optional[HttpConfig] = None):
        self.base_url = base_url.rstrip('/')
        self.config = config or HttpConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self.ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def ensure_client(self):
        """确保client已创建"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                verify=False  # 如果需要禁用SSL验证
            )

    async def close(self):
        """关闭client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, endpoint: str, **kwargs) -> Union[Dict[str, Any], bytes, str]:
        """发送HTTP请求"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        await self.ensure_client()
        response = await self._client.request(method, url, **kwargs)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            data = response.json()
        elif 'application/octet-stream' in content_type:
            data = response.read()
        else:
            data = response.text
        logger.debug(f"HTTP Response: {response.status_code} {response.reason_phrase}")
        return data

    async def get(self, endpoint: str, **kwargs) -> Union[Dict[str, Any], bytes, str]:
        """发送GET请求"""
        return await self.request('GET', endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> Union[Dict[str, Any], bytes, str]:
        """发送POST请求"""
        return await self.request('POST', endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> Union[Dict[str, Any], bytes, str]:
        """发送DELETE请求"""
        return await self.request('DELETE', endpoint, **kwargs) 
    
    async def put(self, endpoint: str, **kwargs) -> Union[Dict[str, Any], bytes, str]:
        """发送PUT请求"""
        return await self.request('PUT', endpoint, **kwargs)