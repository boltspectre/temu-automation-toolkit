import random
import re
from threading import local
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger

from spider_modules.random_ua import generate_random_headers
from config.common_config import db
from utils.proxy_manager import proxy_manager
from config.py_config import config_value

thread_local = local()


class SpiderSession:
    """爬虫会话管理类，每个线程维护一个独立的会话实例"""

    def __init__(self, proxies_list=None, use_proxy=True, force_proxy=False, task_id=None):
        """初始化会话管理

        Args:
            proxies_list: 代理列表，如果为None则不使用代理
            use_proxy: 是否使用代理，默认True
            force_proxy: 是否强制使用代理（不使用本地IP），默认False
            task_id: 任务ID，用于任务级别的IP绑定
        """
        self.use_proxy = use_proxy
        self.force_proxy = force_proxy
        self.task_id = task_id
        self.proxies_list = proxies_list or []
        # 转换代理列表为标准格式
        self.standard_proxies = self._convert_to_standard_format()
        self.used_proxies = set()  # 记录已使用的代理IP
        self.failed_proxies = set()  # 记录失败的代理IP
        self.task_proxy = None  # 任务专属代理IP
        
        # 如果提供了task_id，尝试从数据库获取该任务之前使用的代理IP
        if task_id:
            self.task_proxy = self._get_task_proxy_from_db(task_id)
        
        self.session = self._create_session()
        
        # 优先使用任务专属代理
        if self.task_proxy and self.use_proxy:
            self.proxy = self.task_proxy
            self.used_proxies.add(self._get_proxy_key(self.proxy))
        else:
            self.proxy = self._get_random_proxy() if self.standard_proxies and self.use_proxy else None
            if self.proxy:
                self.used_proxies.add(self._get_proxy_key(self.proxy))
        self._set_session_headers()

    def _convert_to_standard_format(self):
        """将不同格式的代理转换为标准的代理URL格式"""
        standard_proxies = []

        # 正则表达式匹配标准代理格式
        standard_pattern = re.compile(
            r'^(https?|socks5)://'  # 协议
            r'(?:([^:]+):([^@]+)@)?'  # 可选的账号密码
            r'([^:]+):(\d+)$'  # IP和端口
        )

        for proxy in self.proxies_list:
            # 如果是字符串，检查是否为标准格式
            if isinstance(proxy, str):
                if standard_pattern.match(proxy.strip()):
                    standard_proxies.append(proxy.strip())
                else:
                    logger.warning(f"不支持的代理格式: {proxy}")
            # 如果是字典，转换为标准格式
            elif isinstance(proxy, dict):
                try:
                    protocol = proxy.get('protocol', 'socks5')  # 默认使用socks5协议
                    ip = proxy['ip']
                    port = proxy['port']
                    username = proxy.get('username')
                    password = proxy.get('password')

                    if username and password:
                        proxy_url = f"{protocol}://{username}:{password}@{ip}:{port}"
                    else:
                        proxy_url = f"{protocol}://{ip}:{port}"

                    standard_proxies.append(proxy_url)
                except KeyError as e:
                    logger.warning(f"代理字典缺少必要的键 {e}: {proxy}")
            elif not proxy:
                logger.trace(f"代理为空，不使用代理")
            else:
                logger.warning(f"不支持的代理类型: {type(proxy)}")

        return standard_proxies

    def _create_session(self):
        """创建带有重试机制的session"""
        session = Session()

        # 配置重试策略
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504, 403]
        )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _get_proxy_key(self, proxy_dict):
        """获取代理的唯一标识（IP:端口）"""
        if not proxy_dict:
            return None
        # 从http或https键中提取代理URL
        proxy_url = proxy_dict.get('http') or proxy_dict.get('https') or proxy_dict.get('socks5')
        if proxy_url:
            # 提取IP和端口部分（去掉协议和认证信息）
            if '@' in proxy_url:
                proxy_url = proxy_url.split('@')[1]
            return proxy_url
        return None
    
    def _get_task_proxy_from_db(self, task_id):
        """从数据库获取任务之前使用的代理IP"""
        try:
            query = "SELECT ip FROM task WHERE task_id = ? AND ip IS NOT NULL AND ip != ''"
            result = db.execute_sql(query, params=(task_id,), fetch="fetch_one")
            if result and result[0]:
                proxy_str = result[0]
                # 检查代理格式是否标准
                if re.match(r'^(https?|socks5)://', proxy_str):
                    # 转换为字典格式
                    protocol = proxy_str.split('://')[0]
                    return {
                        'http': proxy_str,
                        'https': proxy_str,
                        protocol: proxy_str
                    }
                else:
                    # 自定义格式，转换为标准格式
                    parts = proxy_str.split('/')
                    if len(parts) == 4:
                        ip, port, username, password = parts
                        proxy_url = f"socks5://{username}:{password}@{ip}:{port}"
                        return {
                            'http': proxy_url,
                            'https': proxy_url,
                            'socks5': proxy_url
                        }
        except Exception as e:
            logger.warning(f"从数据库获取任务代理失败: {e}")
        return None
    
    def _save_task_proxy_to_db(self, task_id, proxy_dict):
        """保存任务使用的代理IP到数据库"""
        try:
            logger.debug(f"_save_task_proxy_to_db 被调用，task_id={task_id}, proxy_dict={proxy_dict}")
            
            if not task_id or not proxy_dict:
                logger.warning(f"参数无效，task_id={task_id}, proxy_dict={proxy_dict}")
                return
            
            proxy_key = self._get_proxy_key(proxy_dict)
            if not proxy_key:
                logger.warning(f"无法获取代理键，proxy_dict={proxy_dict}")
                return
            
            # 获取代理URL
            proxy_url = proxy_dict.get('http') or proxy_dict.get('https') or proxy_dict.get('socks5')
            if not proxy_url:
                logger.warning(f"无法获取代理URL，proxy_dict={proxy_dict}")
                return
            
            query = "UPDATE task SET ip = ? WHERE task_id = ?"
            result = db.execute_sql(query, params=(proxy_url, task_id,))
            logger.info(f"已保存任务 {task_id} 的代理IP: {proxy_key}, 更新结果: {result}")
        except Exception as e:
            logger.error(f"保存任务代理到数据库失败: {e}", exc_info=True)

    def _get_random_proxy(self, exclude_failed=True):
        """从代理列表中随机选择一个代理
        
        Args:
            exclude_failed: 是否排除失败的代理，默认True
        """
        if not self.standard_proxies:
            return None

        # 如果需要排除失败的代理
        if exclude_failed and self.failed_proxies:
            available_proxies = [p for p in self.standard_proxies 
                                if self._get_proxy_key(self._convert_proxy_to_dict(p)) not in self.failed_proxies]
            if not available_proxies:
                # 如果所有代理都失败了，且不是强制模式，返回None
                if not self.force_proxy:
                    logger.warning("所有代理都失败了，将使用本地IP")
                    return None
                # 强制模式下，仍然从所有代理中选择
                available_proxies = self.standard_proxies
        else:
            available_proxies = self.standard_proxies

        proxy_url = random.choice(available_proxies)
        # 对于requests库，需要将代理URL放入字典中
        protocol = proxy_url.split('://')[0]
        return {
            'http': proxy_url,
            'https': proxy_url,
            protocol: proxy_url
        }

    def _convert_proxy_to_dict(self, proxy_url):
        """将代理URL转换为字典格式"""
        protocol = proxy_url.split('://')[0]
        return {
            'http': proxy_url,
            'https': proxy_url,
            protocol: proxy_url
        }

    def _switch_proxy(self):
        """切换到下一个可用的代理"""
        if not self.standard_proxies:
            return None
        
        # 如果是强制模式且所有代理都失败了
        if self.force_proxy and len(self.failed_proxies) >= len(self.standard_proxies):
            logger.warning("所有代理都失败了，清空失败列表并重试")
            self.failed_proxies.clear()
            self.used_proxies.clear()
        
        # 获取新的代理
        new_proxy = self._get_random_proxy(exclude_failed=True)
        if new_proxy:
            proxy_key = self._get_proxy_key(new_proxy)
            if proxy_key not in self.used_proxies:
                logger.info(f"切换到新代理: {proxy_key}")
                self.proxy = new_proxy
                self.used_proxies.add(proxy_key)
            else:
                logger.debug(f"代理 {proxy_key} 已使用过，尝试其他代理")
                return self._switch_proxy()
        else:
            # 如果没有可用的代理，且不是强制模式，返回None（使用本地IP）
            if not self.force_proxy:
                logger.info("没有可用的代理，将使用本地IP")
                self.proxy = None
            else:
                logger.error("没有可用的代理，且处于强制代理模式")
        
        return self.proxy

    def _set_session_headers(self):
        """设置会话的请求头"""
        self.session.headers.update(generate_random_headers())

    def refresh_headers(self):
        """刷新会话的请求头，保持一定的随机性"""
        self.session.headers.update(generate_random_headers())
        return self.session.headers

    def _request(self, method, url, max_retries=3, **kwargs):
        """基础请求方法

        Args:
            method: 请求方法，get或post
            url: 请求URL
            max_retries: 最大重试次数，默认3
            **kwargs: 其他请求参数

        Returns:
            Response对象或None
        """
        for attempt in range(max_retries):
            try:
                # 根据配置决定是否使用代理
                proxies = self.proxy if self.use_proxy and self.proxy else None
                
                if proxies:
                    proxy_key = self._get_proxy_key(proxies)
                    logger.debug(f"尝试 {attempt + 1}/{max_retries}: 使用代理 {proxy_key} 请求 {url}")
                else:
                    logger.debug(f"尝试 {attempt + 1}/{max_retries}: 使用本地IP 请求 {url}")
                
                response = self.session.request(
                    method,
                    url,
                    proxies=proxies,
                    timeout=10, **kwargs
                )

                response.raise_for_status()
                
                # 请求成功，保存代理IP到数据库（如果是任务专属代理）
                if self.task_id and proxies:
                    logger.debug(f"准备保存任务 {self.task_id} 的代理IP到数据库")
                    self._save_task_proxy_to_db(self.task_id, proxies)
                else:
                    if not self.task_id:
                        logger.debug("未设置task_id，跳过保存代理IP到数据库")
                    if not proxies:
                        logger.debug("未使用代理，跳过保存代理IP到数据库")
                
                return {
                    "response": response,
                    "ip": proxies,
                }

            except Exception as e:
                logger.error(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                
                # 如果使用代理且请求失败，记录失败的代理
                if self.proxy:
                    proxy_key = self._get_proxy_key(self.proxy)
                    self.failed_proxies.add(proxy_key)
                    logger.warning(f"代理 {proxy_key} 失败，已加入失败列表")
                
                # 如果不是最后一次尝试，尝试切换代理
                if attempt < max_retries - 1:
                    if self.use_proxy and self.standard_proxies:
                        # 尝试切换到下一个代理
                        new_proxy = self._switch_proxy()
                        if new_proxy is None and self.force_proxy:
                            # 强制模式下没有可用代理，直接返回失败
                            logger.error("强制代理模式下无可用代理，请求终止")
                            return {
                                "response": "",
                                "ip": None,
                            }
                        # 刷新请求头
                        self.refresh_headers()
                    else:
                        # 不使用代理或没有代理列表，直接重试
                        self.refresh_headers()
                else:
                    # 最后一次尝试失败，返回空响应
                    return {
                        "response": "",
                        "ip": None,
                    }

    def get(self, url, **kwargs):
        """发送GET请求"""
        return self._request("get", url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        """发送POST请求"""
        return self._request("post", url, data=data, json=json, **kwargs)

    def close(self):
        """关闭会话"""
        self.session.close()


def get_proxies_from_file(file_path="config/proxy.txt"):
    """从文件读取代理列表，支持两种格式：
    1. 自定义格式: ip/端口/账号/密码
    2. 标准格式: socks5://user:pass@ip:port 或 http://ip:port 等
    """
    proxies_list = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # 检查是否为标准格式
                if re.match(r'^(https?|socks5)://', line):
                    proxies_list.append(line)
                else:
                    # 尝试按自定义格式分割：ip/端口/账号/密码
                    parts = line.split("/")
                    if len(parts) == 4:
                        ip, port, username, password = parts
                        proxies_list.append({
                            "ip": ip,
                            "port": port,
                            "username": username,
                            "password": password,
                            "protocol": "socks5"  # 默认使用socks5协议
                        })
                    else:
                        logger.warning(f"不支持的代理格式: {line}")
        return proxies_list, f"代理加载成功"
    except FileNotFoundError:
        return [], f"未找到代理文件 {file_path}，将不使用代理"
    except Exception as e:
        logger.error(f"读取代理文件失败：{e}")
        return [], f"读取代理文件失败：{e}"


def get_proxies_from_manager():
    """从代理管理器获取有效代理列表"""
    try:
        proxies_list = proxy_manager.get_valid_proxies()
        if proxies_list:
            logger.info(f"从代理管理器获取到 {len(proxies_list)} 个有效代理")
        else:
            logger.warning("代理管理器中没有有效代理")
        return proxies_list, f"代理加载成功"
    except Exception as e:
        logger.error(f"从代理管理器获取代理失败：{e}")
        return [], f"从代理管理器获取代理失败：{e}"


def get_proxies_with_backup():
    """获取代理列表，优先从API获取，失败时从文件获取备用代理"""
    try:
        # 优先从代理管理器获取
        proxies_list = proxy_manager.get_valid_proxies()
        if proxies_list:
            logger.info(f"从代理API获取到 {len(proxies_list)} 个代理")
            return proxies_list
    except Exception as e:
        logger.warning(f"从代理API获取代理失败: {e}")
    
    # API获取失败，尝试从文件获取备用代理
    try:
        proxies_list, msg = get_proxies_from_file(file_path=config_value.proxy_file_path)
        logger.info(f"从文件获取备用代理: {msg}")
        return proxies_list
    except Exception as e:
        logger.error(f"从文件获取代理也失败: {e}")
        return []


def get_thread_spider_session(proxies_list=None, use_proxy=True, force_proxy=False, task_id=None):
    """获取当前线程的爬虫会话实例，确保每个线程只有一个实例
    
    Args:
        proxies_list: 代理列表，如果为None则从代理管理器获取
        use_proxy: 是否使用代理，默认True
        force_proxy: 是否强制使用代理（不使用本地IP），默认False
        task_id: 任务ID，用于任务级别的IP绑定
    
    Returns:
        SpiderSession实例
    """
    # 如果没有提供代理列表，尝试从代理管理器获取
    if proxies_list is None:
        proxies_list, msg = get_proxies_from_manager()
        logger.info(msg)
    
    # 如果任务ID存在，使用任务级别的会话
    if task_id:
        session_key = f"spider_session_{task_id}"
        if not hasattr(thread_local, session_key):
            setattr(thread_local, session_key, SpiderSession(proxies_list, use_proxy, force_proxy, task_id))
        return getattr(thread_local, session_key)
    else:
        # 使用线程级别的会话
        if not hasattr(thread_local, "spider_session"):
            thread_local.spider_session = SpiderSession(proxies_list, use_proxy, force_proxy, task_id)
        return thread_local.spider_session


if __name__ == "__main__":
    # 这里获取代理ip列表 使用成功的会记录上 计算当前进行中的代理ip
    proxies_list, msg = get_proxies_from_file(file_path="ip2.txt")
    logger.info(msg)
    proxies_list = []
    session = SpiderSession(proxies_list)
    response = session.get("https://www.baidu.com")
    print(response["response"].text)
    print(response.get("ip"))