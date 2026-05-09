import atexit
import os
import signal
import sys
from loguru import logger


class ProcessGuard:
    """进程守护类，确保程序异常退出时能清理所有子进程"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ProcessGuard._initialized:
            return
        ProcessGuard._initialized = True
        
        self.cleanup_functions = []
        self._register_cleanup_handlers()

    def _register_cleanup_handlers(self):
        """注册清理处理器"""
        try:
            atexit.register(self._cleanup_all)
            
            if sys.platform != 'win32':
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGINT, self._signal_handler)
            
            logger.info("进程守护机制已初始化")
        except Exception as e:
            logger.error(f"注册进程守护处理器失败: {e}")

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"接收到信号 {signum}，开始清理进程...")
        self._cleanup_all()
        sys.exit(0)

    def register_cleanup(self, cleanup_func, name="unknown"):
        """注册清理函数"""
        self.cleanup_functions.append((name, cleanup_func))
        logger.debug(f"注册清理函数: {name}")

    def _cleanup_all(self):
        """执行所有清理函数"""
        if not self.cleanup_functions:
            return
        
        logger.info("开始执行进程清理...")
        for name, cleanup_func in reversed(self.cleanup_functions):
            try:
                logger.info(f"正在清理: {name}")
                cleanup_func()
            except Exception as e:
                logger.error(f"清理 {name} 时出错: {e}")
        
        logger.info("进程清理完成")


process_guard = ProcessGuard()
