"""
代理IP管理模块
提供代理IP的测试、筛选和管理功能
"""
import socket
import threading
import time
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from loguru import logger
from config.common_config import config_manager


class ProxyManager:
    """代理IP管理器 - 统一处理代理IP的测试、筛选和管理"""
    
    def __init__(self):
        self.all_proxies = []  # 所有代理IP
        self.valid_proxies = []  # 有效代理IP
        self.test_lock = threading.Lock()  # 测试锁，防止并发测试
        self.test_history = {}  # 测试历史记录
        self.test_callbacks = []  # 测试完成回调函数列表
    
    def set_proxies(self, proxies: List[str]):
        """
        设置代理IP列表
        :param proxies: 代理IP列表
        """
        self.all_proxies = proxies.copy()
        logger.info(f"已设置 {len(proxies)} 个代理IP")
    
    def get_all_proxies(self) -> List[str]:
        """
        获取所有代理IP
        :return: 所有代理IP列表
        """
        return self.all_proxies.copy()
    
    def get_valid_proxies(self) -> List[str]:
        """
        获取有效代理IP
        :return: 有效代理IP列表
        """
        return self.valid_proxies.copy()
    
    def clean_proxies(self):
        """
        清空代理IP列表
        """
        self.all_proxies.clear()
        self.valid_proxies.clear()
        self.test_history.clear()
        logger.info("已清空所有代理IP")
    
    def test_proxy(self, proxy: str, test_url: str = "https://www.baidu.com", timeout: int = 10) -> bool:
        """
        测试单个代理IP
        :param proxy: 代理IP
        :param test_url: 测试URL
        :param timeout: 超时时间
        :return: True=有效，False=无效
        """
        try:
            proxy_dict = {
                'http': proxy,
                'https': proxy
            }
            logger.info(f"开始测试代理: {proxy}, 测试URL: {test_url}, 超时: {timeout}秒")
            
            response = requests.get(
                test_url,
                proxies=proxy_dict,
                timeout=timeout,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                # 记录测试历史
                self.test_history[proxy] = {
                    'last_test': time.time(),
                    'status': 'valid',
                    'response_time': response.elapsed.total_seconds()
                }
                logger.info(f"代理测试成功: {proxy}, 响应时间: {response.elapsed.total_seconds()}秒")
                return True
            else:
                # 记录测试历史
                self.test_history[proxy] = {
                    'last_test': time.time(),
                    'status': 'invalid',
                    'response_code': response.status_code
                }
                logger.warning(f"代理测试失败: {proxy}, 状态码: {response.status_code}")
                return False
        except Exception as e:
            # 记录测试历史
            self.test_history[proxy] = {
                'last_test': time.time(),
                'status': 'error',
                'error': str(e)
            }
            logger.error(f"代理测试异常: {proxy}, 错误: {str(e)}")
            return False
    
    def test_proxies_sync(self, proxies: List[str] = None, test_url: str = "https://www.baidu.com", timeout: int = None) -> List[str]:
        """
        同步测试代理IP列表
        :param proxies: 代理IP列表，如果为None则测试所有代理
        :param test_url: 测试URL
        :param timeout: 超时时间
        :return: 有效代理IP列表
        """
        if proxies is None:
            proxies = self.all_proxies
        
        if timeout is None:
            # 使用数据库配置管理器获取配置
            timeout_config = config_manager.get_or_set_config("ProxyPage_timeout_edit", "10")
            timeout = int(timeout_config.strip()) if timeout_config.strip() else 10
        
        # 先测试本机IP
        local_ip_test_result = self.test_local_ip(test_url, timeout)
        if not local_ip_test_result:
            logger.warning("本机IP测试失败，可能是网络连接问题，代理IP测试结果可能不准确")
        
        valid_proxies = []
        for proxy in proxies:
            if self.test_proxy(proxy, test_url, timeout):
                valid_proxies.append(proxy)
        
        # 更新有效代理列表
        self.valid_proxies = valid_proxies
        
        # 调用回调函数
        for callback in self.test_callbacks:
            try:
                callback(self.valid_proxies)
            except Exception as e:
                logger.error(f"代理测试回调函数执行失败: {str(e)}")
        
        logger.info(f"代理测试完成，共测试 {len(proxies)} 个，有效 {len(valid_proxies)} 个")
        return valid_proxies
    
    def test_proxies_async(self, proxies: List[str] = None, test_url: str = "https://www.baidu.com", timeout: int = None, callback: Callable = None):
        """
        异步测试代理IP列表
        :param proxies: 代理IP列表，如果为None则测试所有代理
        :param test_url: 测试URL
        :param timeout: 超时时间
        :param callback: 测试完成回调函数
        """
        def test_thread():
            with self.test_lock:
                try:
                    valid_proxies = self.test_proxies_sync(proxies, test_url, timeout)
                    if callback:
                        callback(valid_proxies)
                except Exception as e:
                    logger.error(f"异步代理测试失败: {str(e)}")
        
        thread = threading.Thread(target=test_thread)
        thread.daemon = True
        thread.start()
        logger.info("已启动异步代理测试")
    
    def test_proxies_multithread(self, proxies: List[str] = None, test_url: str = "https://www.baidu.com", timeout: int = None, thread_count: int = 5) -> List[str]:
        """
        多线程测试代理IP列表
        :param proxies: 代理IP列表，如果为None则测试所有代理
        :param test_url: 测试URL
        :param timeout: 超时时间
        :param thread_count: 线程数
        :return: 有效代理IP列表
        """
        if proxies is None:
            proxies = self.all_proxies
        
        if timeout is None:
            timeout_config = config_manager.get_or_set_config("ProxyPage_timeout_edit", "10")
            timeout = int(timeout_config.strip()) if timeout_config.strip() else 10
        
        # 先测试本机IP
        local_ip_test_result = self.test_local_ip(test_url, timeout)
        if not local_ip_test_result:
            logger.warning("本机IP测试失败，可能是网络连接问题，代理IP测试结果可能不准确")
        
        # 使用线程池测试代理
        valid_proxies = []
        results_lock = threading.Lock()
        
        def test_proxy_thread(proxy):
            result = self.test_proxy(proxy, test_url, timeout)
            with results_lock:
                if result:
                    valid_proxies.append(proxy)
            return result
        
        logger.info(f"开始多线程测试代理，线程数: {thread_count}, 代理数: {len(proxies)}")
        
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {executor.submit(test_proxy_thread, proxy): proxy for proxy in proxies}
            
            for future in as_completed(futures):
                proxy = futures[future]
                try:
                    result = future.result()
                    if result:
                        logger.info(f"代理测试成功: {proxy}")
                    else:
                        logger.info(f"代理测试失败: {proxy}")
                except Exception as e:
                    logger.error(f"代理测试异常: {proxy}, 错误: {str(e)}")
        
        # 更新有效代理列表
        self.valid_proxies = valid_proxies
        
        # 调用回调函数
        for callback in self.test_callbacks:
            try:
                callback(self.valid_proxies)
            except Exception as e:
                logger.error(f"代理测试回调函数执行失败: {str(e)}")
        
        logger.info(f"多线程代理测试完成，共测试 {len(proxies)} 个，有效 {len(valid_proxies)} 个")
        return valid_proxies
    
    def add_test_callback(self, callback: Callable):
        """
        添加测试完成回调函数
        :param callback: 回调函数，接收有效代理IP列表作为参数
        """
        self.test_callbacks.append(callback)
    
    def remove_test_callback(self, callback: Callable):
        """
        移除测试完成回调函数
        :param callback: 要移除的回调函数
        """
        if callback in self.test_callbacks:
            self.test_callbacks.remove(callback)
    
    def get_proxy_info(self, proxy: str) -> Optional[Dict]:
        """
        获取代理IP信息
        :param proxy: 代理IP
        :return: 代理IP信息字典
        """
        return self.test_history.get(proxy)
    
    def get_all_proxy_info(self) -> Dict[str, Dict]:
        """
        获取所有代理IP信息
        :return: 所有代理IP信息字典
        """
        return self.test_history.copy()
    
    def is_testing(self) -> bool:
        """
        检查是否正在测试
        :return: True=正在测试，False=未测试
        """
        return self.test_lock.locked()
    
    def use_all_proxies(self):
        """
        将所有代理IP设置为有效代理IP
        """
        self.valid_proxies = self.all_proxies.copy()
        logger.info(f"已将所有 {len(self.valid_proxies)} 个代理IP设置为有效")
    
    @staticmethod
    def get_local_ip() -> str:
        """
        获取本机IP地址
        :return: 本机IP地址
        """
        try:
            # 创建一个socket对象
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 连接到一个公共DNS服务器（不会发送数据，只是用来获取本机IP）
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            logger.error(f"获取本机IP失败: {str(e)}")
            return "127.0.0.1"
    
    def test_local_ip(self, test_url: str = "https://www.baidu.com", timeout: int = 10) -> bool:
        """
        测试本机IP网络连接
        :param test_url: 测试URL
        :param timeout: 超时时间
        :return: True=连接成功，False=连接失败
        """
        local_ip = self.get_local_ip()
        try:
            # 不使用代理，直接连接测试URL
            response = requests.get(
                test_url,
                timeout=timeout,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                logger.info(f"本机IP {local_ip} 测试成功，响应时间: {response.elapsed.total_seconds():.2f}秒")
                return True
            else:
                logger.warning(f"本机IP {local_ip} 测试失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"本机IP {local_ip} 测试异常: {str(e)}")
            return False
    
    def get_random_proxy(self) -> Optional[str]:
        """
        获取随机有效代理IP
        :return: 随机有效代理IP或None
        """
        if not self.valid_proxies:
            return None
        import random
        return random.choice(self.valid_proxies)
    
    def get_proxy_stats(self) -> Dict:
        """
        获取代理IP统计信息
        :return: 统计信息字典
        """
        total = len(self.all_proxies)
        valid = len(self.valid_proxies)
        invalid = total - valid
        
        # 统计测试历史中的状态
        status_count = {'valid': 0, 'invalid': 0, 'error': 0}
        for info in self.test_history.values():
            status = info.get('status', 'unknown')
            if status in status_count:
                status_count[status] += 1
        
        return {
            'total': total,
            'valid': valid,
            'invalid': invalid,
            'valid_rate': valid / total if total > 0 else 0,
            'status_count': status_count,
            'is_testing': self.is_testing()
        }


# 创建全局代理管理器实例
proxy_manager = ProxyManager()


# 便捷函数，保持向后兼容
def set_proxies(proxies: List[str]):
    """设置代理IP列表（便捷函数）"""
    proxy_manager.set_proxies(proxies)


def get_all_proxies() -> List[str]:
    """获取所有代理IP（便捷函数）"""
    return proxy_manager.get_all_proxies()


def get_valid_proxies() -> List[str]:
    """获取有效代理IP（便捷函数）"""
    return proxy_manager.get_valid_proxies()


def clean_proxies():
    """清空代理IP列表（便捷函数）"""
    proxy_manager.clean_proxies()


def test_proxies_sync(proxies: List[str] = None, test_url: str = "https://www.baidu.com", timeout: int = None) -> List[str]:
    """同步测试代理IP列表（便捷函数）"""
    return proxy_manager.test_proxies_sync(proxies, test_url, timeout)


def test_proxies_async(proxies: List[str] = None, test_url: str = "https://www.baidu.com", timeout: int = None, callback: Callable = None):
    """异步测试代理IP列表（便捷函数）"""
    proxy_manager.test_proxies_async(proxies, test_url, timeout, callback)


def use_all_proxies():
    """将所有代理IP设置为有效代理IP（便捷函数）"""
    proxy_manager.use_all_proxies()


def get_random_proxy() -> Optional[str]:
    """获取随机有效代理IP（便捷函数）"""
    return proxy_manager.get_random_proxy()


def get_proxy_stats() -> Dict:
    """获取代理IP统计信息（便捷函数）"""
    return proxy_manager.get_proxy_stats()