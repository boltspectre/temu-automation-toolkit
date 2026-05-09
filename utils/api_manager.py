"""
统一API管理模块
提供所有API服务的统一启动和关闭功能
"""
import threading
import time
from typing import Dict, List, Optional

from loguru import logger
from lite_modules.port_manager import port_manager


class APIManager:
    """API管理器 - 统一管理所有API服务"""
    
    def __init__(self):
        self.api_services = {}  # 存储API服务信息
        self.manager_lock = threading.Lock()
    
    def register_api(self, name: str, start_func, stop_func, port: int, auto_start: bool = False):
        """
        注册API服务
        :param name: API服务名称
        :param start_func: 启动函数
        :param stop_func: 停止函数
        :param port: 端口号
        :param auto_start: 是否自动启动
        """
        with self.manager_lock:
            self.api_services[name] = {
                'start_func': start_func,
                'stop_func': stop_func,
                'port': port,
                'auto_start': auto_start,
                'status': 'stopped'  # stopped, starting, running, stopping
            }
            logger.info(f"已注册API服务: {name} (端口: {port})")
            
            if auto_start:
                self.start_api(name)
    
    def start_api(self, name: str) -> bool:
        """
        启动指定API服务
        :param name: API服务名称
        :return: True=成功，False=失败
        """
        with self.manager_lock:
            if name not in self.api_services:
                logger.error(f"API服务 {name} 未注册")
                return False
            
            service = self.api_services[name]
            if service['status'] == 'running':
                logger.info(f"API服务 {name} 已在运行中")
                return True
            
            try:
                service['status'] = 'starting'
                logger.info(f"正在启动API服务: {name}")
                
                # 先释放端口
                port_manager.release_port(service['port'])
                
                # 启动服务
                service['start_func']()
                service['status'] = 'running'
                
                logger.info(f"API服务 {name} 启动成功")
                return True
            except Exception as e:
                service['status'] = 'stopped'
                logger.error(f"启动API服务 {name} 失败: {str(e)}")
                return False
    
    def stop_api(self, name: str) -> bool:
        """
        停止指定API服务
        :param name: API服务名称
        :return: True=成功，False=失败
        """
        with self.manager_lock:
            if name not in self.api_services:
                logger.error(f"API服务 {name} 未注册")
                return False
            
            service = self.api_services[name]
            if service['status'] == 'stopped':
                logger.info(f"API服务 {name} 已停止")
                return True
            
            try:
                service['status'] = 'stopping'
                logger.info(f"正在停止API服务: {name}")
                
                # 停止服务
                service['stop_func']()
                service['status'] = 'stopped'
                
                # 释放端口
                port_manager.release_port(service['port'])
                
                logger.info(f"API服务 {name} 停止成功")
                return True
            except Exception as e:
                logger.error(f"停止API服务 {name} 失败: {str(e)}")
                return False
    
    def restart_api(self, name: str) -> bool:
        """
        重启指定API服务
        :param name: API服务名称
        :return: True=成功，False=失败
        """
        logger.info(f"重启API服务: {name}")
        if not self.stop_api(name):
            return False
        
        # 等待一段时间确保完全停止
        time.sleep(1)
        
        return self.start_api(name)
    
    def start_all_apis(self) -> Dict[str, bool]:
        """
        启动所有API服务
        :return: 启动结果字典
        """
        results = {}
        with self.manager_lock:
            for name in self.api_services:
                results[name] = self.start_api(name)
        return results
    
    def stop_all_apis(self) -> Dict[str, bool]:
        """
        停止所有API服务
        :return: 停止结果字典
        """
        results = {}
        with self.manager_lock:
            for name in self.api_services:
                results[name] = self.stop_api(name)
        return results
    
    def get_api_status(self, name: str) -> Optional[str]:
        """
        获取API服务状态
        :param name: API服务名称
        :return: 状态字符串或None
        """
        with self.manager_lock:
            if name in self.api_services:
                return self.api_services[name]['status']
            return None
    
    def get_all_api_status(self) -> Dict[str, str]:
        """
        获取所有API服务状态
        :return: 状态字典
        """
        with self.manager_lock:
            return {name: service['status'] for name, service in self.api_services.items()}
    
    def get_api_info(self, name: str) -> Optional[Dict]:
        """
        获取API服务信息
        :param name: API服务名称
        :return: 服务信息字典或None
        """
        with self.manager_lock:
            if name in self.api_services:
                service = self.api_services[name].copy()
                # 移除函数对象，避免序列化问题
                service.pop('start_func', None)
                service.pop('stop_func', None)
                return service
            return None
    
    def get_all_api_info(self) -> Dict[str, Dict]:
        """
        获取所有API服务信息
        :return: 所有服务信息字典
        """
        with self.manager_lock:
            result = {}
            for name, service in self.api_services.items():
                info = service.copy()
                # 移除函数对象，避免序列化问题
                info.pop('start_func', None)
                info.pop('stop_func', None)
                result[name] = info
            return result
    
    def unregister_api(self, name: str) -> bool:
        """
        注销API服务
        :param name: API服务名称
        :return: True=成功，False=失败
        """
        with self.manager_lock:
            if name not in self.api_services:
                logger.error(f"API服务 {name} 未注册")
                return False
            
            # 先停止服务
            self.stop_api(name)
            
            # 移除注册
            del self.api_services[name]
            logger.info(f"已注销API服务: {name}")
            return True
    
    def get_running_apis(self) -> List[str]:
        """
        获取正在运行的API服务列表
        :return: 正在运行的API服务名称列表
        """
        with self.manager_lock:
            return [name for name, service in self.api_services.items() if service['status'] == 'running']
    
    def get_stopped_apis(self) -> List[str]:
        """
        获取已停止的API服务列表
        :return: 已停止的API服务名称列表
        """
        with self.manager_lock:
            return [name for name, service in self.api_services.items() if service['status'] == 'stopped']


# 创建全局API管理器实例
api_manager = APIManager()


# 便捷函数，保持向后兼容
def register_api(name: str, start_func, stop_func, port: int, auto_start: bool = False):
    """注册API服务（便捷函数）"""
    api_manager.register_api(name, start_func, stop_func, port, auto_start)


def start_api(name: str) -> bool:
    """启动API服务（便捷函数）"""
    return api_manager.start_api(name)


def stop_api(name: str) -> bool:
    """停止API服务（便捷函数）"""
    return api_manager.stop_api(name)


def restart_api(name: str) -> bool:
    """重启API服务（便捷函数）"""
    return api_manager.restart_api(name)


def start_all_apis() -> Dict[str, bool]:
    """启动所有API服务（便捷函数）"""
    return api_manager.start_all_apis()


def stop_all_apis() -> Dict[str, bool]:
    """停止所有API服务（便捷函数）"""
    return api_manager.stop_all_apis()


def get_api_status(name: str) -> Optional[str]:
    """获取API服务状态（便捷函数）"""
    return api_manager.get_api_status(name)


def get_all_api_status() -> Dict[str, str]:
    """获取所有API服务状态（便捷函数）"""
    return api_manager.get_all_api_status()