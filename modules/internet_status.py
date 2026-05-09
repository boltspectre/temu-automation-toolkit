import os
import socket
import subprocess
from typing import Tuple

import requests


class NetworkChecker:
    def __init__(self):
        # 可信服务器列表（多协议、多节点，降低单点依赖）
        self.check_targets = {
            # ICMP (ping) 检测目标（高可用性DNS服务器）
            "icmp": ["114.114.114.114", "8.8.8.8", "223.5.5.5"],
            # TCP 端口检测（HTTP/HTTPS默认端口）
            "tcp": [("www.baidu.com", 80), ("www.aliyun.com", 443)],
            # HTTP 验证（返回固定内容的可信接口，如百度首页）
            "http": ["http://www.baidu.com", "http://www.taobao.com"]
        }
        # 禁用代理（防止通过代理伪造网络状态）
        self.no_proxy = {"http": None, "https": None}

    def _ping(self, host: str, timeout: int = 2) -> bool:
        """ICMP ping检测（跨平台实现）"""
        param = "-n 1" if os.name == "nt" else "-c 1"  # Windows用-n，Linux用-c
        command = ["ping", param, "-W", str(timeout), host]
        try:
            # 执行ping命令，隐藏输出
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout + 1
            )
            return result.returncode == 0  # 0表示成功
        except (subprocess.TimeoutExpired, Exception):
            return False

    def _tcp_connect(self, host: str, port: int, timeout: int = 2) -> bool:
        """TCP端口连接检测"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((host, port))
                return result == 0  # 0表示连接成功
        except (socket.timeout, socket.error, Exception):
            return False

    def _http_verify(self, url: str, timeout: int = 3) -> bool:
        """HTTP请求验证（检查响应合法性）"""
        try:
            response = requests.get(
                url,
                proxies=self.no_proxy,
                timeout=timeout,
                allow_redirects=True
            )
            # 验证状态码和响应内容（避免连接到伪造的本地服务器）
            return response.status_code == 200 and len(response.content) > 1000
        except (requests.exceptions.RequestException, Exception):
            return False

    def is_connected(self) -> Tuple[bool, str]:
        """
        综合检测网络状态
        返回：(是否联网, 检测结果描述)
        """
        # 1. 检查本地网络接口是否启用（基础过滤）
        try:
            # 尝试连接本地非路由地址，仅检查网卡是否启用
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM).connect(("10.255.255.255", 1))
        except socket.error:
            return False, "本地网络接口未启用"

        # 2. 多协议、多目标检测（至少满足一半以上目标）
        success_count = 0
        total_checks = 0
        details = []

        # TCP检测
        for host, port in self.check_targets["tcp"]:
            total_checks += 1
            if self._tcp_connect(host, port):
                success_count += 1
                details.append(f"TCP成功: {host}:{port}")
            else:
                details.append(f"TCP失败: {host}:{port}")

        # HTTP检测
        for url in self.check_targets["http"]:
            total_checks += 1
            if self._http_verify(url):
                success_count += 1
                details.append(f"HTTP成功: {url}")
            else:
                details.append(f"HTTP失败: {url}")

        # 判定：超过1/2的检测成功则认为联网（可根据严格程度调整阈值）
        is_online = success_count / total_checks > 0.5
        status = "在线" if is_online else "离线"
        return is_online, f"网络状态: {status}。检测详情: {'; '.join(details)}"


# 使用示例（强制验证逻辑）
if __name__ == "__main__":
    checker = NetworkChecker()
    is_online, msg = checker.is_connected()

    # 强制逻辑：若检测为离线，只能使用离线功能
    if not is_online:
        print("检测到离线状态，仅启用离线功能。")
        # 执行离线登录/功能逻辑
    else:
        print("检测到在线状态，执行在线验证流程。")
        # 执行在线登录验证逻辑
