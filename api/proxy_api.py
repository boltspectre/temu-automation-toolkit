# api/proxy_api.py
import multiprocessing
import subprocess
import sys
import time

import psutil
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.py_config import config_value
from lite_modules.port_killer import release_port
from lite_modules.port_manager import port_manager
from utils.process_guard import process_guard

# 导入代理路由
from api.proxy_routes.proxy_routes import router as proxy_router

# 创建 FastAPI 应用实例
app = FastAPI()

# 允许跨域请求（以便前端页面可以访问接口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册代理路由
app.include_router(proxy_router, tags=["代理接口"])

# 全局变量
main_proxy_process = None


def run_proxy_server(target_port: int):
    """后台代理API运行函数"""
    try:
        uvicorn.run(
            "api.proxy_api:app",
            host="127.0.0.1",
            port=target_port,
            workers=1,
            reload=False
        )
    except Exception as e:
        logger.error(f"代理API服务器启动失败，端口 {target_port} 可能被占用: {e}")
        time.sleep(1)
        sys.exit(1)


def start_proxy_api():
    """启动代理API服务（使用multiprocessing.Process）"""
    global main_proxy_process
    
    if main_proxy_process and main_proxy_process.is_alive():
        logger.info("代理API服务器已在运行，无需重复启动")
        return True
    
    target_port = int(config_value.api_proxy_port)
    logger.info(f"准备启动代理API服务，端口：{target_port}")

    # 先全部停止对应端口进程（使用port_killer的release_port函数）
    logger.info(f"使用port_killer释放代理API端口 {target_port}")
    success = release_port(target_port, force=True)
    if success:
        logger.info(f"代理API端口 {target_port} 释放成功")
    else:
        logger.error(f"代理API端口 {target_port} 释放失败，尝试使用port_manager作为备选方案")
        # 尝试使用port_manager作为备选方案
        if not port_manager.release_port(target_port):
            logger.error("无法释放端口，API启动失败")
            return False
    
    # 等待一段时间确保端口完全释放
    time.sleep(0.5)
    
    # 再次检查端口是否真的释放了
    if port_manager.is_port_in_use(target_port):
        logger.warning(f"端口 {target_port} 仍被占用，尝试强制释放")
        # 使用更强制的方式
        # 强制杀死所有占用该端口的进程
        try:
            result = subprocess.run(f'netstat -ano | findstr :{target_port}', shell=True, capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if line.strip() and ('LISTENING' in line or 'ESTABLISHED' in line):
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                            logger.info(f"强制终止占用端口 {target_port} 的进程 PID={pid}")
                        except Exception as e:
                            logger.error(f"强制终止进程失败: {e}")
        except Exception as e:
            logger.error(f"强制释放端口 {target_port} 失败: {e}")
        
        # 再次等待和检查
        time.sleep(0.5)
        if port_manager.is_port_in_use(target_port):
            logger.error(f"端口 {target_port} 仍被占用，无法启动代理API服务器")
            return False
    
    # 启动进程
    main_proxy_process = multiprocessing.Process(
        target=run_proxy_server,
        args=(target_port,),
        daemon=True
    )
    main_proxy_process.start()
    logger.info(f"代理API服务器进程已启动（PID={main_proxy_process.pid}）")
    
    # 使用统一端口管理器注册进程
    port_manager.register_process(
        name="proxy_api",
        process=main_proxy_process,
        thread=None,
        stop_event=None,
        port=target_port
    )
    
    process_guard.register_cleanup(stop_proxy_api, "代理API进程")
    
    return True


def stop_proxy_api(timeout: int = 5):
    """停止代理API服务（使用multiprocessing.Process）"""
    global main_proxy_process
    
    if not main_proxy_process:
        logger.info("无运行中的代理API服务器进程，无需停止")
        return True
    
    # 跳过已停止的进程
    if not main_proxy_process.is_alive():
        logger.info(f"代理API服务器进程（PID={main_proxy_process.pid if main_proxy_process.pid else '未知'}）已停止，跳过")
        main_proxy_process = None
        return True
    
    try:
        # 获取主进程对象（带异常保护）
        try:
            parent_proc = psutil.Process(main_proxy_process.pid)
        except psutil.NoSuchProcess:
            logger.info(f"代理API服务器进程（PID={main_proxy_process.pid}）已不存在，跳过")
            main_proxy_process = None
            return True
        
        # 终止子进程（递归）
        child_procs = parent_proc.children(recursive=True)
        if child_procs:
            for child in child_procs:
                try:
                    logger.info(f"终止代理API服务器的子进程：PID={child.pid}")
                    child.terminate()
                except psutil.NoSuchProcess:
                    logger.info(f"代理API子进程PID={child.pid}已不存在，跳过")
                except Exception as e:
                    logger.warning(f"终止子进程PID={child.pid}失败：{str(e)}")
            
            # 等待子进程终止（带超时）
            _, still_alive = psutil.wait_procs(child_procs, timeout=timeout)
            for alive_child in still_alive:
                try:
                    logger.warning(f"强制终止代理API服务器的子进程：PID={alive_child.pid}")
                    alive_child.kill()
                except Exception as e:
                    logger.error(f"强制杀死代理API子进程PID={alive_child.pid}失败：{str(e)}")
        
        # 终止主进程
        logger.info(f"终止代理API服务器进程（主进程）：PID={main_proxy_process.pid}")
        main_proxy_process.terminate()
        main_proxy_process.join(timeout=timeout)  # 等待主进程终止（带超时）
        
        # 检查主进程是否仍存活，强制杀死
        if main_proxy_process.is_alive():
            try:
                logger.error(f"代理API服务器进程（PID={main_proxy_process.pid}）超时，强制杀死")
                parent_proc.kill()
                main_proxy_process.join(timeout=1)  # 短暂等待强制杀死结果
            except Exception as e:
                logger.error(f"强制杀死代理API服务器主进程PID={main_proxy_process.pid}失败：{str(e)}")
    
    except Exception as e:
        logger.error(f"终止代理API服务器进程（PID={main_proxy_process.pid if main_proxy_process.pid else '未知'}）出错：{str(e)}")
    
    # 清空进程列表（确保彻底清理）
    main_proxy_process = None
    logger.info("代理API服务器进程已停止，进程列表已清空")


def close_proxy_api():
    """关闭代理API服务（兼容旧接口）"""
    return stop_proxy_api(timeout=5)


# --------------------------
# 单独运行测试（本地调试用）
# --------------------------
if __name__ == "__main__":
    try:
        start_proxy_api()
        print("Press Ctrl+C to stop...")
        import time
        while True:
            time.sleep(1)  # 保持主进程运行
    except KeyboardInterrupt:
        stop_proxy_api()
        print("Shutdown complete.")