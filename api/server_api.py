# api/server_api.py
import multiprocessing
import os
import sys
import subprocess
import threading
import time
import urllib
from contextlib import asynccontextmanager

import psutil
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi_cdn_host import monkey_patch_for_docs_ui
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, Response

from api.server_routes import common_routes, shop_routes, task_routes, server_routes
from config.py_config import config_value
from lite_modules.port_manager import port_manager
from lite_modules.port_killer import release_port
from utils.multiThreading_log_manager import get_task_log_manager
from utils.process_guard import process_guard

# 解决Nuitka打包后模块路径问题
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(current_dir))

# 导入各模块路由
from config.common_config import config_manager

APP_VERSION = config_value.current_version
APP_INFO = config_value.app_info


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI生命周期管理（替代@app.on_event）
    - 进入：启动时执行（每个工作进程仅执行1次）
    - 退出：关闭时执行（可选，用于资源清理）
    """
    # 启动逻辑（原startup钩子代码，每个工作进程初始化任务管理器）
    log_manager = get_task_log_manager()
    log_manager.start()  # 启动任务管理器（轮询线程、初始化等）
    logger.info(f"✅ FastAPI工作进程[{os.getpid()}] 任务管理器初始化并启动成功")

    yield  # 必须有yield，分隔启动/退出逻辑，执行完启动逻辑后挂起，服务运行中

    # 退出逻辑（可选，进程关闭时执行，用于优雅停止任务管理器）
    log_manager.stop()  # 调用任务管理器的stop方法，优雅终止所有任务/线程
    logger.info(f"✅ FastAPI工作进程[{os.getpid()}] 任务管理器已优雅停止")


# 创建FastAPI实例
app = FastAPI(
    title="Ikun联盟-接口文档",
    description="基于FastAPI的本地分页接口模板，支持多进程启动、认证、通用分页查询",
    version=APP_VERSION,
    lifespan=lifespan
)


monkey_patch_for_docs_ui(app)


# 全局中间件：添加版本号响应头
class VersionHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['X-App-Version'] = APP_VERSION
        response.headers['X-App-AppInfo'] = urllib.parse.quote(APP_INFO)
        return response

app.add_middleware(VersionHeaderMiddleware)

# 配置静态资源和模板
static_dir = os.path.join(os.path.dirname(current_dir), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(current_dir), "templates"))


# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册各模块路由（关键：将拆分的路由注册到主应用）
app.include_router(common_routes.router, tags=["通用接口"])
app.include_router(shop_routes.router, tags=["店铺接口"])
app.include_router(task_routes.router, tags=["任务接口"])
app.include_router(server_routes.router, tags=["服务器接口"])

# 暴露templates供其他模块使用
app.state.templates = templates


# 全局变量
thread_exit_lock = threading.Lock()
main_gui_process = []
main_gui_server_time_thread = None
main_gui_thread_exit_flag = False


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(static_dir, "favicon.ico")
    # 检查文件是否存在，避免报错
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    # 文件不存在时返回空响应，避免500错误
    return Response(status_code=204)

def run_server(external_ip, port, worker_count):
    """后台任务管理运行函数"""
    try:
        uvicorn.run(
            "api.server_api:app",
            host=external_ip,
            port=port,
            workers=worker_count,
            reload=False
        )
    except Exception as e:
        logger.error(f"服务器启动失败，端口 {port} 可能被占用: {e}")
        # 给进程一些时间来确保错误信息被记录
        time.sleep(1)
        # 退出进程，让主进程知道启动失败
        sys.exit(1)

def start_main_api():
    """启动批量FastAPI后台任务管理"""
    global main_gui_process
    if main_gui_process:
        for proc in main_gui_process:
            if proc.is_alive():
                logger.info("已有后台任务管理进程在运行中，无需重复启动")
                return None
        main_gui_process.clear()
    
    # 设置服务器启动时间
    try:
        from api.server_routes.server_routes import set_server_start_time
        set_server_start_time()
    except Exception as e:
        logger.error(f"设置服务器启动时间失败: {e}")

    # 从配置管理器获取服务器配置
    external_ip = config_manager.get_or_set_config("ServerPage_external_ip", "localhost") or "localhost"
    base_port = int(config_manager.get_or_set_config("ServerPage_port", "1234"))
    process_count = int(config_manager.get_or_set_config("ServerPage_process_count", "1"))
    worker_per_proc = int(config_manager.get_or_set_config("ServerPage_worker_per_proc", "1"))

    # 导入端口管理模块
    try:
        port_killer_available = True
    except ImportError as e:
        logger.error(f"无法导入port_killer模块: {e}")
        port_killer_available = False

    # 先全部停止对应端口进程（使用port_killer的release_port函数）
    for current_port in range(base_port, base_port + process_count):
        # 使用port_killer的release_port函数，确保彻底清除
        logger.info(f"使用port_killer释放端口 {current_port}")
        success = release_port(current_port, force=True)
        if success:
            logger.info(f"端口 {current_port} 释放成功")
        else:
            logger.error(f"端口 {current_port} 释放失败，服务器可能启动失败")
            # 尝试使用port_manager作为备选方案
            port_manager.release_port(current_port)
        
        # 等待一段时间确保端口完全释放
        time.sleep(0.5)
        
        # 再次检查端口是否真的释放了
        if port_manager.is_port_in_use(current_port):
            logger.warning(f"端口 {current_port} 仍被占用，尝试强制释放")
            # 使用更强制的方式
            try:
                import subprocess
                # 强制杀死所有占用该端口的进程
                result = subprocess.run(f'netstat -ano | findstr :{current_port}', shell=True, capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if line.strip() and ('LISTENING' in line or 'ESTABLISHED' in line):
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            try:
                                subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                                logger.info(f"强制终止占用端口 {current_port} 的进程 PID={pid}")
                            except Exception as e:
                                logger.error(f"强制终止进程失败: {e}")
            except Exception as e:
                logger.error(f"强制释放端口 {current_port} 失败: {e}")
            
            # 再次等待和检查
            time.sleep(1)
            if port_manager.is_port_in_use(current_port):
                logger.error(f"端口 {current_port} 强制释放后仍被占用，服务器启动可能失败")
            else:
                logger.info(f"端口 {current_port} 强制释放成功")

    logger.info("开始启动服务")

    for i in range(process_count):
        current_port = base_port + i
        proc = multiprocessing.Process(
            target=run_server,
            args=(external_ip, current_port, worker_per_proc),
            daemon=True
        )
        proc.start()
        main_gui_process.append(proc)
        logger.info(f"服务器进程{i + 1}/{process_count} 已启动：PID={proc.pid}，端口={current_port}，worker数={worker_per_proc}")
    
    # 等待一段时间，让所有进程尝试启动
    time.sleep(2)
    
    # 检查所有进程是否还在运行
    failed_processes = []
    for i, proc in enumerate(main_gui_process):
        if not proc.is_alive():
            failed_processes.append(i + 1)
            logger.error(f"服务器进程{i + 1} 启动失败，可能端口被占用")
    
    # 如果有进程启动失败，停止所有进程并退出
    if failed_processes:
        logger.error(f"共有 {len(failed_processes)} 个服务器进程启动失败: {failed_processes}")
        logger.info("正在停止所有已启动的进程...")
        stop_main_api_process()
        logger.error("由于端口冲突，服务器启动失败")
        sys.exit(1)
    
    logger.info(f"批量启动完成，共{len(main_gui_process)}个服务器管理进程")

    process_guard.register_cleanup(stop_main_api_process, "服务器API进程")

    return main_gui_process

def stop_main_api_process(timeout: int = 5):
    """
    停止所有后台任务管理进程
    :param timeout: 进程终止超时时间（秒），默认5秒
    """

    global main_gui_process
    if not main_gui_process:
        # logger.info("无运行中的后台任务管理进程，无需停止")
        return

    # 遍历进程列表（使用副本，避免遍历时修改原列表）
    for idx, proc in enumerate(main_gui_process.copy()):
        # 跳过已停止的进程
        if not proc.is_alive():
            logger.info(f"服务器进程{idx + 1}（PID={proc.pid if proc.pid else '未知'}）已停止，跳过")
            continue

        try:
            # 获取主进程对象（带异常保护）
            try:
                parent_proc = psutil.Process(proc.pid)
            except psutil.NoSuchProcess:
                logger.info(f"服务器进程{idx + 1}（PID={proc.pid}）已不存在，跳过")
                continue

            # 终止子进程（递归）
            child_procs = parent_proc.children(recursive=True)
            if child_procs:
                for child in child_procs:
                    try:
                        logger.info(f"终止服务器进程{idx + 1}的子进程：PID={child.pid}")
                        child.terminate()
                    except psutil.NoSuchProcess:
                        logger.info(f"服务器子进程PID={child.pid}已不存在，跳过")
                    except Exception as e:
                        logger.warning(f"终止子进程PID={child.pid}失败：{str(e)}")

                # 等待子进程终止（带超时）
                _, still_alive = psutil.wait_procs(child_procs, timeout=timeout)
                for alive_child in still_alive:
                    try:
                        logger.warning(f"强制终止服务器进程{idx + 1}的子进程：PID={alive_child.pid}")
                        alive_child.kill()
                    except Exception as e:
                        logger.error(f"强制杀死服务器子进程PID={alive_child.pid}失败：{str(e)}")

            # 终止主进程
            logger.info(f"终止服务器进程{idx + 1}（主进程）：PID={proc.pid}")
            proc.terminate()
            proc.join(timeout=timeout)  # 等待主进程终止（带超时）

            # 检查主进程是否仍存活，强制杀死
            if proc.is_alive():
                try:
                    logger.error(f"服务器进程{idx + 1}（PID={proc.pid}）超时，强制杀死")
                    parent_proc.kill()
                    proc.join(timeout=1)  # 短暂等待强制杀死结果
                except Exception as e:
                    logger.error(f"强制杀死服务器主进程PID={proc.pid}失败：{str(e)}")

        except Exception as e:
            logger.error(f"终止服务器进程{idx + 1}（PID={proc.pid if proc.pid else '未知'}）出错：{str(e)}")

    # 清空进程列表（确保彻底清理）
    main_gui_process.clear()
    logger.info("所有服务器管理进程已停止，进程列表已清空")


def server_time_action(cycle_time):
    """周期任务线程函数（优化退出逻辑）"""
    global main_gui_thread_exit_flag
    # logger.info(f"周期线程开始运行，总周期：{cycle_time}秒，分段休眠检测退出标志")

    # 剩余休眠时间
    remaining_sleep = cycle_time

    while True:
        # 检查退出标志（加锁保证线程安全）
        with thread_exit_lock:
            if main_gui_thread_exit_flag:
                # logger.info("检测到退出标志，周期线程准备退出")
                return

        # 分段休眠（每次休眠1秒，快速响应退出）
        sleep_step = min(1, remaining_sleep)
        time.sleep(sleep_step)
        remaining_sleep -= sleep_step

        # 休眠完成，执行重启逻辑
        if remaining_sleep <= 0:
            logger.info("周期休眠完成，执行服务器重启")
            try:
                restart_main_api()
            except Exception as e:
                logger.error(f"周期重启服务器失败：{str(e)}")
            # 重置剩余休眠时间
            remaining_sleep = cycle_time


def start_cycle_thread():
    """启动周期重启线程"""
    global main_gui_server_time_thread, main_gui_thread_exit_flag

    # 先停止已有线程
    if main_gui_server_time_thread and main_gui_server_time_thread.is_alive():
        logger.info("周期线程已在运行中，先停止原有线程")
        stop_cycle_thread()

    restart_interval = config_manager.get_or_set_config("ServerPage_restart_interval", "1小时")

    try:
        hours = float(restart_interval.replace('小时', ''))
        cycle_time = int(hours * 3600)
    except (ValueError, TypeError):
        logger.error(f"无效的重启间隔：{restart_interval}，使用默认值1小时")
        cycle_time = 3600

    # 重置退出标志
    with thread_exit_lock:
        main_gui_thread_exit_flag = False

    # 测试重启
    # cycle_time = 20

    main_gui_server_time_thread = threading.Thread(
        target=server_time_action,
        args=(cycle_time,),
        name="ServerCycleThread"  # 命名线程，便于调试
    )
    main_gui_server_time_thread.daemon = True
    main_gui_server_time_thread.start()
    logger.info(f"周期线程已启动，周期：{cycle_time}秒，线程ID：{main_gui_server_time_thread.ident}")


# ========== 核心修改：停止周期线程函数 ==========
def stop_cycle_thread():
    """停止周期线程（优化退出逻辑）"""
    global main_gui_server_time_thread, main_gui_thread_exit_flag

    if not (main_gui_server_time_thread and main_gui_server_time_thread.is_alive()):
        # logger.info("周期线程未在运行，无需停止")
        return

    logger.info(f"开始停止周期线程（ID：{main_gui_server_time_thread.ident}）")

    # 设置退出标志（加锁）
    with thread_exit_lock:
        main_gui_thread_exit_flag = True

    # 等待线程退出（超时5秒）
    main_gui_server_time_thread.join(timeout=5)

    # 检查线程状态
    if main_gui_server_time_thread.is_alive():
        logger.warning(f"周期线程（ID：{main_gui_server_time_thread.ident}）未能正常终止，尝试强制清理")
        # 重置线程对象（放弃等待，避免内存泄漏）
        main_gui_server_time_thread = None
        main_gui_thread_exit_flag = False
    else:
        logger.info(f"周期线程（ID：{main_gui_server_time_thread.ident}）停止成功")
        main_gui_server_time_thread = None
        main_gui_thread_exit_flag = False

def restart_main_api():
    """重启后台任务管理"""
    # 先彻底停止所有进程
    stop_main_api_process(timeout=10)  # 增加超时时间，确保完全停止
    
    # 等待一段时间确保所有进程完全退出
    time.sleep(2)
    
    # 再次检查并释放端口（防止残留进程）
    base_port = int(config_manager.get_or_set_config("ServerPage_port", "1234"))
    process_count = int(config_manager.get_or_set_config("ServerPage_process_count", "1"))
    
    for current_port in range(base_port, base_port + process_count):
        logger.info(f"重启时再次检查并释放端口 {current_port}")
        success = release_port(current_port, force=True)
        if not success:
            logger.error(f"重启时端口 {current_port} 释放失败")
            # 使用更强制的方式
            try:
                result = subprocess.run(f'netstat -ano | findstr :{current_port}', shell=True, capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if line.strip() and ('LISTENING' in line or 'ESTABLISHED' in line):
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            try:
                                subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                                logger.info(f"重启时强制终止占用端口 {current_port} 的进程 PID={pid}")
                            except Exception as e:
                                logger.error(f"重启时强制终止进程失败: {e}")
            except Exception as e:
                logger.error(f"重启时强制释放端口 {current_port} 失败: {e}")
    
    # 再次等待确保端口完全释放
    time.sleep(1)
    
    # 启动新服务
    start_main_api()


# 启动服务器线程
def start_temu_task_process():
    try:
        multiprocessing.freeze_support()
        start_main_api()
    except KeyboardInterrupt:
        stop_main_api_process()
        stop_cycle_thread()
        logger.info("服务已手动停止")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    start_main_api()
    start_cycle_thread()  # 可选：启动周期重启线程
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_main_api_process()
        stop_cycle_thread()
        logger.info("服务已手动停止")