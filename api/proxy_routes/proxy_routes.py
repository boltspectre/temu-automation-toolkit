# api/proxy_routes/proxy_routes.py
from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from utils.proxy_manager import proxy_manager

# 创建路由实例
router = APIRouter()

class ProxyRequest(BaseModel):
    proxies: list[str]  # 直接在顶层定义代理列表
    test_url: str = "https://www.baidu.com"  # 测试URL，默认百度
    thread_count: int = 5  # 测试线程数，默认5

class LocalIPTestRequest(BaseModel):
    test_url: str = "https://www.baidu.com"  # 测试URL，默认百度
    timeout: int = 10  # 超时时间，默认10秒

@router.post("/send_proxies")
async def receive_proxies(request: ProxyRequest):
    """接收代理IP列表"""
    proxy_manager.set_proxies(request.proxies)
    return {
        "code": "1",
        "message": f"成功接收 {len(request.proxies)} 个代理",
        "received_proxies": request.proxies,
        "count": len(request.proxies)
    }

@router.get("/")
async def hello_api_get():
    """API连通性测试（GET）"""
    return {
        "code": "1",
        "method":  "GET",
        "message": "API连通性测试成功"
    }

@router.post("/")
async def hello_api_post():
    """API连通性测试（POST）"""
    return {
        "code": "1",
        "method": "POST",
        "message": "API连通性测试成功"
    }

@router.get("/get_proxies")
async def get_proxies():
    """获取有效代理IP列表"""
    valid_proxies = proxy_manager.get_valid_proxies()
    return {
        "code": "1",
        "proxies": valid_proxies,
        "count": len(valid_proxies),
        "message": "成功获取已选用代理ip"
    }

@router.get("/get_all_proxies")
async def get_all_proxies():
    """获取所有代理IP列表"""
    all_proxies = proxy_manager.get_all_proxies()
    return {
        "code": "1",
        "proxies": all_proxies,
        "count": len(all_proxies),
        "message": "成功获取全部代理ip"
    }

@router.get("/clean_proxies")
async def clean_proxies():
    """清空代理IP列表"""
    proxy_manager.clean_proxies()
    return {
        "code": "1",
        "proxies": [],
        "count": 0,
        "message": "已清空代理列表"
    }

@router.post("/test_proxy")
async def test_proxy(request: ProxyRequest):
    """测试代理IP列表"""
    # 检查是否有正在进行的测试
    if proxy_manager.is_testing():
        all_proxies = proxy_manager.get_all_proxies()
        valid_proxies = proxy_manager.get_valid_proxies()
        local_ip = proxy_manager.get_local_ip()
        return {
            "code": "-1",
            "total": len(all_proxies),
            "valid": len(valid_proxies),
            "valid_proxies": valid_proxies,
            "local_ip": local_ip,
            "message": "已有测试正在进行，请稍后再试"
        }

    # 先测试本机IP
    local_ip = proxy_manager.get_local_ip()
    local_ip_test_result = proxy_manager.test_local_ip(request.test_url)
    
    # 设置代理列表
    proxy_manager.set_proxies(request.proxies)
    
    # 多线程测试代理（等待测试完成）
    logger.info(f"开始多线程测试 {len(request.proxies)} 个代理，线程数: {request.thread_count}...")
    valid_proxies = proxy_manager.test_proxies_multithread(
        proxies=request.proxies,
        test_url=request.test_url,
        thread_count=request.thread_count
    )
    
    return {
        "code": "1",
        "total": len(request.proxies),
        "valid": len(valid_proxies),
        "valid_proxies": valid_proxies,
        "local_ip": local_ip,
        "local_ip_test_result": "success" if local_ip_test_result else "failed",
        "test_url": request.test_url,
        "thread_count": request.thread_count,
        "message": f"代理IP测试完成，本机IP {local_ip} 测试{'成功' if local_ip_test_result else '失败'}，有效代理 {len(valid_proxies)} 个"
    }

@router.get("/test_proxy_result")
async def get_test_result():
    """获取代理测试结果"""
    all_proxies = proxy_manager.get_all_proxies()
    valid_proxies = proxy_manager.get_valid_proxies()
    stats = proxy_manager.get_proxy_stats()
    
    # 获取本机IP信息
    local_ip = proxy_manager.get_local_ip()
    
    return {
        "code": "1",
        "total": len(all_proxies),
        "valid": len(valid_proxies),
        "valid_proxies": valid_proxies,
        "stats": stats,
        "is_testing": proxy_manager.is_testing(),
        "local_ip": local_ip,
        "message": "获取代理测试结果成功"
    }

@router.get("/test_proxy_use_all")
def test_proxy_use_all():
    """将所有代理IP设置为有效代理IP"""
    proxy_manager.use_all_proxies()
    all_proxies = proxy_manager.get_all_proxies()
    return {
        "code": "1",
        "total": len(all_proxies),
        "valid": len(all_proxies),
        "valid_proxies": all_proxies,
        "message": "已将所有代理IP设置为有效"
    }

@router.post("/test_local_ip")
async def test_local_ip(request: LocalIPTestRequest):
    """测试本机IP网络连接"""
    local_ip = proxy_manager.get_local_ip()
    test_result = proxy_manager.test_local_ip(request.test_url, request.timeout)
    
    if test_result:
        return {
            "code": "1",
            "local_ip": local_ip,
            "test_result": "success",
            "test_url": request.test_url,
            "message": f"本机IP {local_ip} 测试成功"
        }
    else:
        return {
            "code": "0",
            "local_ip": local_ip,
            "test_result": "failed",
            "test_url": request.test_url,
            "message": f"本机IP {local_ip} 测试失败"
        }

@router.get("/get_local_ip")
async def get_local_ip():
    """获取本机IP地址"""
    local_ip = proxy_manager.get_local_ip()
    return {
        "code": "1",
        "local_ip": local_ip,
        "message": "获取本机IP成功"
    }

@router.get("/get_proxy_stats")
def get_proxy_stats():
    """获取代理IP统计信息"""
    stats = proxy_manager.get_proxy_stats()
    return {
        "code": "1",
        "stats": stats,
        "message": "获取代理统计信息成功"
    }

@router.get("/get_random_proxy")
def get_random_proxy():
    """获取随机有效代理IP"""
    proxy = proxy_manager.get_random_proxy()
    if proxy:
        return {
            "code": "1",
            "proxy": proxy,
            "message": "获取随机代理成功"
        }
    else:
        return {
            "code": "-1",
            "proxy": None,
            "message": "无可用代理IP"
        }