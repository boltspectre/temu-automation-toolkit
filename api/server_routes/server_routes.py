# api/server_routes.py
from datetime import datetime

from fastapi import APIRouter, Depends
from loguru import logger
from starlette.responses import JSONResponse

from api.server_routes.auth import verify_token
from config.common_config import config_manager

# 创建路由实例
router = APIRouter()

# 全局变量，存储服务器启动时间（仅用于缓存）
server_start_time = None

def set_server_start_time():
    """设置服务器启动时间（存储到数据库）"""
    global server_start_time
    try:
        # 获取当前时间
        now = datetime.now()
        time_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # 存储到配置管理器
        config_manager.upsert_config("server_start_time", time_str)
        
        # 更新缓存
        server_start_time = now
        logger.info(f"服务器启动时间已设置: {time_str}")
    except Exception as e:
        logger.error(f"设置服务器启动时间失败: {e}")

def get_server_start_time():
    """获取服务器启动时间（从数据库读取）"""
    global server_start_time
    
    # 如果缓存中有值，直接返回
    if server_start_time:
        return server_start_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 否则从数据库读取
    try:
        time_str = config_manager.get_or_set_config("server_start_time", None)
        
        if time_str:
            # 解析时间字符串
            server_start_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return time_str
    except Exception as e:
        logger.error(f"获取服务器启动时间失败: {e}")
    
    return None

def get_server_start_time_obj():
    """获取服务器启动时间（datetime对象）"""
    global server_start_time
    
    # 如果缓存中有值，直接返回
    if server_start_time:
        return server_start_time
    
    # 否则从数据库读取
    try:
        time_str = config_manager.get_or_set_config("server_start_time", None)
        
        if time_str:
            server_start_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return server_start_time
    except Exception as e:
        logger.error(f"获取服务器启动时间对象失败: {e}")
    
    return None

def calculate_uptime():
    """计算服务器运行时长"""
    start_time = get_server_start_time_obj()
    if start_time:
        now = datetime.now()
        delta = now - start_time
        
        # 计算小时和分钟
        total_seconds = delta.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        
        return f"{hours}小时{minutes}分钟"
    return "0小时0分钟"

# -------------------------- 服务器控制接口 --------------------------
@router.get("/api/server_status", dependencies=[Depends(verify_token)])
def get_server_status_api():
    """获取服务器状态"""
    try:
        return {
            "success": True,
            "running": True,
            "start_time": get_server_start_time() or "未知",
            "uptime": calculate_uptime(),
            "version": "1.0.0",
            "processes": []
        }
    except Exception as e:
        logger.error(f"获取服务器状态失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )



@router.get("/api/get_effect_settings", dependencies=[Depends(verify_token)])
def get_effect_settings_api():
    """获取特效效果设置"""
    try:
        settings = {
            "yinghua_html": config_manager.get_or_set_config("Settings_yinghua_html", "是"),
            "qipao_html": config_manager.get_or_set_config("Settings_qipao_html", "是"),
            "rose_html": config_manager.get_or_set_config("Settings_rose_html", "否"),
            "theme": config_manager.get_or_set_config("Settings_theme", "默认主题"),
            "background_music_enabled": config_manager.get_or_set_config("background_music_enabled", "是") == "是",
            "background_music_autoplay": config_manager.get_or_set_config("background_music_autoplay", "否") == "是",
            "background_music_url": config_manager.get_or_set_config("background_music_url", "https://link.hhtjim.com/163/3355136306.mp3"),
            "background_music_local": config_manager.get_or_set_config("background_music_local", "否") == "是",
            "cdn_mode": config_manager.get_or_set_config("Settings_cdn_mode", "云端")
        }
        return {
            "success": True,
            "data": settings
        }
    except Exception as e:
        logger.error(f"获取特效设置失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.post("/api/save_effect_settings", dependencies=[Depends(verify_token)])
def save_effect_settings_api(request_data: dict):
    """保存特效效果设置"""
    try:
        # 获取当前设置
        current_yinghua = config_manager.get_or_set_config("Settings_yinghua_html", "是")
        current_qipao = config_manager.get_or_set_config("Settings_qipao_html", "是")
        current_rose = config_manager.get_or_set_config("Settings_rose_html", "否")
        current_theme = config_manager.get_or_set_config("Settings_theme", "默认主题")
        current_background_music_enabled = config_manager.get_or_set_config("background_music_enabled", "是")
        current_background_music_autoplay = config_manager.get_or_set_config("background_music_autoplay", "否")
        current_background_music_url = config_manager.get_or_set_config("background_music_url", "https://link.hhtjim.com/163/3355136306.mp3")
        current_background_music_local = config_manager.get_or_set_config("background_music_local", "否")
        current_cdn_mode = config_manager.get_or_set_config("Settings_cdn_mode", "云端")
        
        # 保存各项设置
        config_manager.upsert_config("Settings_yinghua_html", request_data.get("yinghua_html", "是"))
        config_manager.upsert_config("Settings_qipao_html", request_data.get("qipao_html", "是"))
        config_manager.upsert_config("Settings_rose_html", request_data.get("rose_html", "否"))
        config_manager.upsert_config("Settings_theme", request_data.get("theme", "默认主题"))
        config_manager.upsert_config("background_music_enabled", request_data.get("background_music_enabled", "是"))
        config_manager.upsert_config("background_music_autoplay", request_data.get("background_music_autoplay", "否"))
        config_manager.upsert_config("background_music_url", request_data.get("background_music_url", "https://link.hhtjim.com/163/3355136306.mp3"))
        config_manager.upsert_config("background_music_local", request_data.get("background_music_local", "否"))
        config_manager.upsert_config("Settings_cdn_mode", request_data.get("cdn_mode", "云端"))
        
        # 检查是否有变化，如果特效设置有变化，需要刷新页面
        need_refresh = (
            current_yinghua != request_data.get("yinghua_html", "是") or
            current_qipao != request_data.get("qipao_html", "是") or
            current_rose != request_data.get("rose_html", "否") or
            current_theme != request_data.get("theme", "默认主题") or
            current_background_music_enabled != request_data.get("background_music_enabled", "是") or
            current_background_music_autoplay != request_data.get("background_music_autoplay", "否") or
            current_background_music_url != request_data.get("background_music_url", "https://link.hhtjim.com/163/3355136306.mp3") or
            current_background_music_local != request_data.get("background_music_local", "否") or
            current_cdn_mode != request_data.get("cdn_mode", "混合")
        )
        
        return {
            "success": True,
            "message": "特效设置保存成功",
            "need_refresh": need_refresh
        }
    except Exception as e:
        logger.error(f"保存特效设置失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.post("/api/start_server", dependencies=[Depends(verify_token)])
def start_server_api():
    """启动服务器"""
    try:
        return {
            "success": True,
            "message": "服务器启动成功"
        }
    except Exception as e:
        logger.error(f"启动服务器失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.post("/api/stop_server", dependencies=[Depends(verify_token)])
def stop_server_api():
    """停止服务器"""
    try:
        return {
            "success": True,
            "message": "服务器停止成功"
        }
    except Exception as e:
        logger.error(f"停止服务器失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.post("/api/restart_server", dependencies=[Depends(verify_token)])
def restart_server_api():
    """重启服务器"""
    try:
        return {
            "success": True,
            "message": "服务器重启成功"
        }
    except Exception as e:
        logger.error(f"重启服务器失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

# -------------------------- 设置管理接口 --------------------------
@router.get("/api/get_settings", dependencies=[Depends(verify_token)])
def get_settings_api():
    """获取系统设置"""
    try:
        settings = {
            "internal_ip": config_manager.get_or_set_config("internal_ip", "127.0.0.1"),
            "external_ip": config_manager.get_or_set_config("external_ip", "localhost"),
            "port": config_manager.get_or_set_config("port", "1234"),
            "process_count": config_manager.get_or_set_config("process_count", "1"),
            "worker_per_proc": config_manager.get_or_set_config("worker_per_proc", "1"),
            "token": config_manager.get_or_set_config("token", ""),
            "thread_mode": config_manager.get_or_set_config("thread_mode", "0"),
            "mode": config_manager.get_or_set_config("mode", "0"),
            "restart_interval": config_manager.get_or_set_config("restart_interval", "不重启"),
            "cdn_mode": config_manager.get_or_set_config("Settings_cdn_mode", "混合"),
            "background_music_enabled": config_manager.get_or_set_config("background_music_enabled", "是"),
            "background_music_autoplay": config_manager.get_or_set_config("background_music_autoplay", "否"),
            "background_music_url": config_manager.get_or_set_config("background_music_url", ""),
            "background_music_local": config_manager.get_or_set_config("background_music_local", "否")
        }
        return {
            "success": True,
            "data": settings
        }
    except Exception as e:
        logger.error(f"获取设置失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.post("/api/save_settings", dependencies=[Depends(verify_token)])
def save_settings_api(request_data: dict):
    """保存系统设置"""
    try:
        # 保存各项设置
        config_manager.upsert_config("internal_ip", request_data.get("internal_ip", "127.0.0.1"))
        config_manager.upsert_config("external_ip", request_data.get("external_ip", "localhost"))
        config_manager.upsert_config("port", request_data.get("port", "1234"))
        config_manager.upsert_config("process_count", request_data.get("process_count", "1"))
        config_manager.upsert_config("worker_per_proc", request_data.get("worker_per_proc", "1"))
        config_manager.upsert_config("token", request_data.get("token", ""))
        config_manager.upsert_config("thread_mode", request_data.get("thread_mode", "0"))
        config_manager.upsert_config("mode", request_data.get("mode", "0"))
        config_manager.upsert_config("restart_interval", request_data.get("restart_interval", "不重启"))
        config_manager.upsert_config("Settings_cdn_mode", request_data.get("cdn_mode", "混合"))
        config_manager.upsert_config("background_music_enabled", request_data.get("background_music_enabled", "否"))
        config_manager.upsert_config("background_music_autoplay", request_data.get("background_music_autoplay", "否"))
        config_manager.upsert_config("background_music_url", request_data.get("background_music_url", ""))
        config_manager.upsert_config("background_music_local", request_data.get("background_music_local", "否"))
        
        return {
            "success": True,
            "message": "设置保存成功"
        }
    except Exception as e:
        logger.error(f"保存设置失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )