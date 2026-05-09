# api/auth.py
from fastapi import Query, HTTPException

from config.common_config import config_manager


def verify_token(token: str = Query(..., description="认证令牌,必传参,值可为空")):
    """验证请求中的token"""
    auth_enabled = config_manager.get_or_set_config("ServerPage_auth", "False").lower() == "true"
    server_token = config_manager.get_or_set_config("ServerPage_token", "ikun")
    
    if auth_enabled:
        if token != server_token:
            raise HTTPException(
                status_code=403,
                detail="认证失败：token 不正确",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return token