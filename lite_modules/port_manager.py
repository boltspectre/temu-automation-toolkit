"""
统一端口管理模块
提供端口检测、释放和进程管理的通用功能
"""
import os
import platform
import re
import socket
import subprocess
import threading
from typing import List, Optional, Tuple

import psutil
from loguru import logger


class PortManager:
    """端口管理器 - 统一处理端口检测、释放和进程管理"""
    
    def __init__(self):
        self.running_processes = {}  # 存储正在运行的进程信息
        self.process_lock = threading.Lock()
    
    def is_port_in_use(self, port: int, host: str = '0.0.0.0') -> bool:
        """
        检测指定端口是否被占用
        :param port: 要检测的端口
        :param host: 绑定的主机（默认0.0.0.0，兼容IPv4/IPv6）
        :return: True=被占用，False=未占用
        """
        try:
            # 创建socket并尝试绑定端口
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 允许端口复用（仅测试用）
                s.bind((host, port))
            return False
        except OSError:
            return True
    
    def get_listening_pid(self, port: int) -> Optional[int]:
        """
        只获取"正在监听端口"的进程PID（排除TIME_WAIT）
        :param port: 目标端口
        :return: 进程PID或None
        """
        try:
            result = subprocess.run(
                ["netstat", "-ano", f"|findstr :{port}"],
                shell=True,
                capture_output=True,
                text=True,
                encoding="gbk"
            )
            for line in result.stdout.strip().split("\n"):
                if "LISTENING" in line:
                    parts = line.strip().split()
                    pid = int(parts[-1])
                    logger.warning(f"端口 {port} 被进程占用：PID={pid}，启动失败，请关闭进程或更换端口")
                    return pid
            logger.info(f"端口 {port} 无占用进程，启动成功")
            return None
        except Exception as e:
            logger.error(f"获取端口 {port} PID失败：{str(e)}")
            return None
    
    def kill_process_by_pid(self, pid: int, force: bool = True) -> bool:
        """
        根据PID结束进程
        :param pid: 进程ID
        :param force: 是否强制结束（True=强制，False=正常退出）
        :return: True=成功，False=失败
        """
        try:
            process = psutil.Process(pid)
            # 获取进程信息（便于日志）
            process_name = process.name()
            logger.info(f"找到占用端口的进程：PID={pid}，名称={process_name}")

            # 正常终止进程
            if force:
                process.kill()  # 强制杀死（等同于kill -9）
            else:
                process.terminate()  # 正常退出（等同于kill）

            # 等待进程结束
            process.wait(timeout=5)
            logger.info(f"进程 {pid} ({process_name}) 已成功结束")
            return True
        except psutil.NoSuchProcess:
            logger.warning(f"进程 {pid} 不存在")
            return False
        except psutil.AccessDenied:
            logger.error(f"无权限结束进程 {pid}（请以管理员/root身份运行）")
            return False
        except Exception as e:
            logger.error(f"结束进程 {pid} 失败：{e}")
            return False
    
    def kill_listening_process(self, port: int) -> bool:
        """
        杀死"正在监听端口"的进程（只处理真占用）
        :param port: 目标端口
        :return: True=成功，False=失败
        """
        pid = self.get_listening_pid(port)
        if not pid:
            return True  # 无LISTENING进程，无需kill

        try:
            if not psutil.pid_exists(pid):
                logger.warning(f"PID={pid} 不存在，无需kill")
                return True

            proc = psutil.Process(pid)
            # 先杀子进程，再杀主进程
            for child in proc.children(recursive=True):
                child.terminate()
                child.wait(timeout=2)
                if child.is_running():
                    child.kill()

            proc.terminate()
            proc.wait(timeout=3)
            if proc.is_running():
                proc.kill()
                logger.warning(f"PID={pid} 强制杀死")
            else:
                logger.info(f"PID={pid} 正常关闭")
            return True
        except psutil.AccessDenied:
            logger.error(f"无权限杀死PID={pid}（系统进程）")
            return False
        except Exception as e:
            logger.error(f"杀死PID={pid} 失败：{str(e)}")
            return False
    
    def release_port_windows_cmd(self, port: int) -> bool:
        """
        Windows下释放端口的命令行方式
        :param port: 目标端口
        :return: True=成功，False=失败
        """
        try:
            # 1. 查找所有占用端口的PID（包括IPv6）
            cmd = f'netstat -ano -p tcp | findstr /r /c:":{port} "'
            result = subprocess.check_output(cmd, shell=True, encoding='gbk', errors='ignore').strip()
            if not result:
                return True

            # 提取所有唯一的PID
            pid_pattern = re.compile(r'\s+(\d+)$', re.MULTILINE)
            pids = pid_pattern.findall(result)
            pids = list(set(pids))  # 去重

            if not pids:
                logger.error(f"无法提取端口 {port} 的占用PID")
                return False

            # 2. 逐个终止PID
            for pid in pids:
                if not pid.isdigit():
                    continue
                try:
                    kill_cmd = f'taskkill /F /PID {pid}'
                    subprocess.check_output(kill_cmd, shell=True, stderr=subprocess.PIPE)
                    logger.info(f"释放端口 {port} (PID={pid}) 成功")
                except subprocess.CalledProcessError:
                    pass
            return True
        except subprocess.CalledProcessError:
            return False
        except Exception as e:
            logger.error(f"释放端口 {port} 异常: {str(e)}")
            return False
    
    def release_port(self, port: int, force: bool = True) -> bool:
        """
        释放指定端口（杀死所有占用该端口的进程）
        :param port: 目标端口
        :param force: 是否强制结束进程
        :return: True=释放成功，False=释放失败/端口未被占用
        """
        # 1. 检测端口是否被占用
        if not self.is_port_in_use(port):
            logger.info(f"端口 {port} 未被占用，无需释放")
            return True

        # 2. 根据平台选择释放方式
        if platform.system() == "Windows":
            # Windows优先用cmd方式
            release_success = self.release_port_windows_cmd(port) or self.kill_listening_process(port)
        else:
            release_success = self.kill_listening_process(port)

        # 3. 验证端口是否释放
        if self.is_port_in_use(port):
            logger.error(f"端口 {port} 仍被占用（可能有隐藏进程）")
            return False
        else:
            logger.info(f"端口 {port} 已成功释放")
            return True
    
    def register_process(self, name: str, process, thread, stop_event, port: int):
        """
        注册正在运行的进程
        :param name: 进程名称
        :param process: 进程对象
        :param thread: 线程对象
        :param stop_event: 停止事件
        :param port: 端口号
        """
        with self.process_lock:
            self.running_processes[name] = {
                'process': process,
                'thread': thread,
                'stop_event': stop_event,
                'port': port
            }
            logger.info(f"已注册进程: {name} (端口: {port})")
    
    def unregister_process(self, name: str):
        """
        注销进程
        :param name: 进程名称
        """
        with self.process_lock:
            if name in self.running_processes:
                del self.running_processes[name]
                logger.info(f"已注销进程: {name}")
    
    def stop_process(self, name: str, timeout: int = 5) -> bool:
        """
        停止指定进程
        :param name: 进程名称
        :param timeout: 超时时间
        :return: True=成功，False=失败
        """
        with self.process_lock:
            if name not in self.running_processes:
                logger.info(f"进程 {name} 未运行，无需停止")
                return True
            
            proc_info = self.running_processes[name]
            process = proc_info['process']
            thread = proc_info['thread']
            stop_event = proc_info['stop_event']
            port = proc_info['port']
            
            # 设置停止事件
            if stop_event:
                stop_event.set()
            
            # 等待线程结束
            if thread and thread.is_alive():
                thread.join(timeout=timeout)
            
            # 终止进程
            if process:
                try:
                    if hasattr(process, 'terminate'):
                        process.terminate()
                        process.join(timeout=timeout)
                        if process.is_alive():
                            process.kill()
                    elif hasattr(process, 'is_alive') and process.is_alive():
                        # 对于线程，直接等待
                        pass
                except Exception as e:
                    logger.error(f"停止进程 {name} 失败: {str(e)}")
            
            # 释放端口
            self.release_port(port)
            
            # 注销进程
            self.unregister_process(name)
            
            logger.info(f"进程 {name} 已停止")
            return True
    
    def stop_all_processes(self, timeout: int = 5):
        """
        停止所有注册的进程
        :param timeout: 超时时间
        """
        with self.process_lock:
            process_names = list(self.running_processes.keys())
        
        for name in process_names:
            self.stop_process(name, timeout)
        
        logger.info("所有进程已停止")
    
    def get_process_info(self, name: str) -> Optional[dict]:
        """
        获取进程信息
        :param name: 进程名称
        :return: 进程信息字典或None
        """
        with self.process_lock:
            return self.running_processes.get(name, None)
    
    def get_all_processes(self) -> dict:
        """
        获取所有进程信息
        :return: 所有进程信息字典
        """
        with self.process_lock:
            return self.running_processes.copy()


# 创建全局端口管理器实例
port_manager = PortManager()


# 便捷函数，保持向后兼容
def is_port_in_use(port: int, host: str = '0.0.0.0') -> bool:
    """检测端口是否被占用（便捷函数）"""
    return port_manager.is_port_in_use(port, host)


def get_listening_pid(port: int) -> Optional[int]:
    """获取监听端口的PID（便捷函数）"""
    return port_manager.get_listening_pid(port)


def kill_process_by_pid(pid: int, force: bool = True) -> bool:
    """根据PID杀死进程（便捷函数）"""
    return port_manager.kill_process_by_pid(pid, force)


def release_port(port: int, force: bool = True) -> bool:
    """释放端口（便捷函数）"""
    return port_manager.release_port(port, force)


def release_port_windows_cmd(port: int) -> bool:
    """Windows下释放端口（便捷函数）"""
    return port_manager.release_port_windows_cmd(port)