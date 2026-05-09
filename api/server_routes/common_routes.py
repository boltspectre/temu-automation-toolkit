# api/common_routes.py
import ast

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from loguru import logger
from starlette.responses import JSONResponse

from api.server_routes.auth import verify_token
from config.common_config import config_manager, encryptor

# 创建路由实例
router = APIRouter()

# -------------------------- 通用接口 --------------------------
@router.get("/test", dependencies=[Depends(verify_token)])
async def root():
    """基础连通性测试"""
    return {
        "code": 1,
        "success": True,
        "message": "服务运行中",
    }

@router.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_token)])
async def index(request: Request):
    """预留网页路由"""
    try:
        from config.permission_manager import permission_manager
        code_project_mode = permission_manager.load_permissions()

        # 获取樱花效果配置，默认开启
        Settings_yinghua_html = config_manager.get_or_set_config("Settings_yinghua_html", "是")
        # 获取气泡效果配置，默认开启
        Settings_qipao_html = config_manager.get_or_set_config("Settings_qipao_html", "是")
        # 获取Rose效果配置，默认关闭
        Settings_rose_html = config_manager.get_or_set_config("Settings_rose_html", "否")
        # 获取主题配置，默认主题
        Settings_theme = config_manager.get_or_set_config("Settings_theme", "默认主题")
        # 获取背景音乐配置
        background_music_enabled = config_manager.get_or_set_config("background_music_enabled", "是")
        background_music_autoplay = config_manager.get_or_set_config("background_music_autoplay", "否")
        background_music_url = config_manager.get_or_set_config("background_music_url", "https://link.hhtjim.com/163/3355136306.mp3")
        background_music_local = config_manager.get_or_set_config("background_music_local", "否")

        templates = request.app.state.templates
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "title": "任务管理",
                "code_project_mode": code_project_mode,
                "Settings_yinghua_html": Settings_yinghua_html,
                "Settings_qipao_html": Settings_qipao_html,
                "Settings_rose_html": Settings_rose_html,
                "Settings_theme": Settings_theme,
                "background_music_enabled": background_music_enabled,
                "background_music_autoplay": background_music_autoplay,
                "background_music_url": background_music_url,
                "background_music_local": background_music_local,
            }
        )
    except Exception as e:
        logger.error(f"加载HTML模板失败：{str(e)}")
        return HTMLResponse(content="<h1>模板加载失败</h1><p>请检查templates文件夹和index.html是否存在</p>")

@router.get("/api/get_token")
async def get_token_api():
    """获取Token"""
    token = config_manager.get_or_set_config("ServerPage_token", "ikun")
    return {
        "success": True,
        "token": token,
        "message": "获取Token成功"
    }

@router.get("/api/get_token")
async def get_token_api():
    """获取Token"""
    token = config_manager.get_or_set_config("ServerPage_token", "ikun")
    return {
        "success": True,
        "token": token,
        "message": "获取Token成功"
    }



@router.get("/api/get_settings", dependencies=[Depends(verify_token)])
async def get_settings_api():
    """获取服务器配置接口"""
    try:
        # 从配置管理器获取所有配置
        settings = {
            "internal_ip": config_manager.get_or_set_config("ServerPage_internal_ip", ""),
            "external_ip": config_manager.get_or_set_config("ServerPage_external_ip", "localhost"),
            "port": config_manager.get_or_set_config("ServerPage_port", "1234"),
            "process_count": config_manager.get_or_set_config("ServerPage_process_count", "1"),
            "worker_per_proc": config_manager.get_or_set_config("ServerPage_worker_per_proc", "1"),
            "token": config_manager.get_or_set_config("ServerPage_token", ""),
            "auth_enabled": config_manager.get_or_set_config("ServerPage_auth", "False").lower() == "true",
            "thread_mode": config_manager.get_or_set_config("ServerPage_thread_mode", "0"),
            "mode": config_manager.get_or_set_config("ServerPage_mode", "0"),
            "restart_interval": config_manager.get_or_set_config("ServerPage_restart_interval", "不重启"),
            # 日志管理配置
            "auto_clean_log_enabled": config_manager.get_or_set_config("auto_clean_log_enabled", "否"),
            "log_char_threshold": config_manager.get_or_set_config("log_char_threshold", "100000"),
            "log_keep_ratio": config_manager.get_or_set_config("log_keep_ratio", "0.1"),
            # 背景音乐设置
            "background_music_enabled": config_manager.get_or_set_config("background_music_enabled", "是"),
            "background_music_autoplay": config_manager.get_or_set_config("background_music_autoplay", "否"),
            "background_music_url": config_manager.get_or_set_config("background_music_url", "https://link.hhtjim.com/163/3355136306.mp3"),
            "background_music_local": config_manager.get_or_set_config("background_music_local", "否"),
            "cdn_mode": config_manager.get_or_set_config("Settings_cdn_mode", "云端")
        }

        return {
            "success": True,
            "data": settings
        }

    except Exception as e:
        logger.error(f"获取设置失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取配置失败：{str(e)}"}
        )


@router.post("/api/save_settings", dependencies=[Depends(verify_token)])
async def save_settings_api(request: Request):
    """保存服务器配置接口
        {
          "internal_ip": "192.168.0.1",
          "external_ip": "localhost",
          "port": "1234",        // 也可以传数字1234，接口自动转字符串
          "process_count": "1",  // 也可以传数字1，接口自动转字符串
          "token": "abc123",
          "thread_mode": "0",    // 也可以传数字0，接口自动转字符串
          "mode": "0",           // 也可以传数字0，接口自动转字符串
          "restart_interval": "0.5小时"  // 前端直接传这个文本，接口直接保存
        }
    """
    try:

        # 1. 直接解析前端JSON参数（前端传的就是最终要保存的格式）
        params = await request.json()
        logger.info(f"接收配置参数：{params}")

        # 2. 保存其他配置（不包括token）
        # 内网IP（前端传字符串，如"192.168.0.1"）
        if "internal_ip" in params:
            config_manager.upsert_config("ServerPage_internal_ip", params["internal_ip"].strip())
        # 公网IP（前端传字符串，如"124.151.139.82"）
        if "external_ip" in params:
            config_manager.upsert_config("ServerPage_external_ip", params["external_ip"].strip())
        # 端口（前端传字符串/数字都可，统一转字符串保存）
        if "port" in params:
            config_manager.upsert_config("ServerPage_port", str(params["port"]).strip())
        # 进程数（前端传字符串/数字都可，统一转字符串保存）
        if "process_count" in params:
            config_manager.upsert_config("ServerPage_process_count", str(params["process_count"]).strip())
        # 每进程Worker数（前端传字符串/数字都可，统一转字符串保存）
        if "worker_per_proc" in params:
            config_manager.upsert_config("ServerPage_worker_per_proc", str(params["worker_per_proc"]).strip())
        # 线程模式（前端传索引字符串/数字，如"0"/0，统一转字符串）
        if "thread_mode" in params:
            config_manager.upsert_config("ServerPage_thread_mode", str(params["thread_mode"]).strip())
        # 运行模式（前端传索引字符串/数字，如"0"/0，统一转字符串）
        if "mode" in params:
            config_manager.upsert_config("ServerPage_mode", str(params["mode"]).strip())
        # 重启间隔（前端直接传文本，如"0.5小时"/"1小时"/"不重启"，直接保存）
        if "restart_interval" in params:
            config_manager.upsert_config("ServerPage_restart_interval", params["restart_interval"].strip())
        # 启用认证
        if "auth_enabled" in params:
            config_manager.upsert_config("ServerPage_auth", "true" if params["auth_enabled"] else "False")
        
        # 日志管理配置
        # 启用自动清理日志
        if "auto_clean_log_enabled" in params:
            config_manager.upsert_config("auto_clean_log_enabled", params["auto_clean_log_enabled"])
        # 日志字符阈值
        if "log_char_threshold" in params:
            config_manager.upsert_config("log_char_threshold", str(params["log_char_threshold"]))
        # 保留比例
        if "log_keep_ratio" in params:
            config_manager.upsert_config("log_keep_ratio", str(params["log_keep_ratio"]))
        
        # 背景音乐设置
        if "background_music_enabled" in params:
            config_manager.upsert_config("background_music_enabled", params["background_music_enabled"])
        if "background_music_autoplay" in params:
            config_manager.upsert_config("background_music_autoplay", params["background_music_autoplay"])
        if "background_music_url" in params:
            config_manager.upsert_config("background_music_url", params["background_music_url"])
        if "background_music_local" in params:
            config_manager.upsert_config("background_music_local", params["background_music_local"])
        if "cdn_mode" in params:
            config_manager.upsert_config("Settings_cdn_mode", params["cdn_mode"])
        
        # 重新加载日志清理器配置
        try:
            from utils.log_cleaner import reload_log_cleaner_config
            reload_log_cleaner_config()
            logger.info("日志清理器配置已重新加载")
        except Exception as e:
            logger.warning(f"重新加载日志清理器配置失败: {e}")

        # 3. 最后保存token，确保使用最新的token进行验证
        # Token（前端传字符串，如"abc123"）
        if "token" in params:
            config_manager.upsert_config("ServerPage_token", params["token"].strip())

        # 4. 返回成功响应
        return {
            "success": True,
            "message": "配置保存成功"
        }

    except Exception as e:
        logger.error(f"保存设置失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"保存配置失败：{str(e)}"}
        )


@router.get("/get_setting")
async def get_setting(name: str):
    """获取指定配置项"""
    try:
        value = config_manager.get_or_set_config(name, "")
        return {
            "success": True,
            "value": value
        }
    except Exception as e:
        logger.error(f"获取配置失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取配置失败：{str(e)}"}
        )


@router.post("/api/get_config", dependencies=[Depends(verify_token)])
async def get_config_api(request: Request):
    """获取指定配置项（POST方式）
    {
        "key": "配置键名"
    }
    """
    try:
        params = await request.json()
        key = params.get("key", "")
        if not key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "配置键名不能为空"}
            )
        value = config_manager.get_or_set_config(key, "")
        return {
            "success": True,
            "data": value
        }
    except Exception as e:
        logger.error(f"获取配置失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取配置失败：{str(e)}"}
        )


@router.post("/api/set_config", dependencies=[Depends(verify_token)])
async def set_config_api(request: Request):
    """设置指定配置项
    {
        "key": "配置键名",
        "value": "配置值"
    }
    """
    try:
        params = await request.json()
        key = params.get("key", "")
        value = params.get("value", "")
        if not key:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "配置键名不能为空"}
            )
        config_manager.upsert_config(key, value)
        return {
            "success": True,
            "message": "配置保存成功"
        }
    except Exception as e:
        logger.error(f"保存配置失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"保存配置失败：{str(e)}"}
        )


# -------------------------- 本地音乐接口 --------------------------
@router.get("/api/local_music_list", dependencies=[Depends(verify_token)])
async def get_local_music_list():
    """获取本地音乐文件列表"""
    try:
        import os
        music_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "配置文件_资源配置", "music")
        if not os.path.exists(music_dir):
            return {"success": True, "data": []}
        
        music_files = []
        for f in sorted(os.listdir(music_dir)):
            if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac')):
                music_files.append({
                    "name": os.path.splitext(f)[0],
                    "filename": f,
                    "url": f"/api/local_music/{f}"
                })
        
        return {"success": True, "data": music_files}
    except Exception as e:
        logger.error(f"获取本地音乐列表失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )


@router.get("/api/local_music/{filename}", dependencies=[Depends(verify_token)])
async def get_local_music(filename: str):
    """播放本地音乐文件"""
    try:
        import os
        from fastapi.responses import FileResponse
        
        music_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "配置文件_资源配置", "music")
        file_path = os.path.join(music_dir, filename)
        
        # 安全检查：防止路径遍历
        if not os.path.abspath(file_path).startswith(os.path.abspath(music_dir)):
            return JSONResponse(status_code=403, content={"error": "非法路径"})
        
        if not os.path.exists(file_path):
            return JSONResponse(status_code=404, content={"error": "文件不存在"})
        
        # 根据扩展名设置MIME类型
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.flac': 'audio/flac',
            '.aac': 'audio/aac'
        }
        media_type = mime_types.get(ext, 'audio/mpeg')
        
        return FileResponse(file_path, media_type=media_type)
    except Exception as e:
        logger.error(f"播放本地音乐失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


