import os
import platform
import re
import socket
import subprocess

import psutil
from loguru import logger


def is_port_in_use(port: int, host: str = '0.0.0.0') -> bool:
    """
    检测指定端口是否被占用
    :param port: 要检测的端口
    :param host: 绑定的主机（默认0.0.0.0，兼容IPv4/IPv6）
    :return: True=被占用，False=未占用
    """
    # 先尝试IPv4
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
        return False
    except OSError:
        pass
    
    # 再尝试IPv6
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('::', port))
        return False
    except OSError:
        pass
    
    # 如果IPv4和IPv6都绑定失败，说明端口被占用
    return True


def get_process_id_using_port(port: int) -> list[int]:
    """
    获取占用指定端口的所有进程PID
    :param port: 目标端口
    :return: 进程PID列表（空列表=无占用）
    """
    pids = []
    try:
        # 遍历所有IPv4网络连接
        for conn in psutil.net_connections(kind='inet'):
            # 匹配端口（conn.laddr是元组：(ip, port)）
            if conn.laddr and conn.laddr.port == port and conn.pid:
                pids.append(conn.pid)
        
        # 遍历所有IPv6网络连接
        for conn in psutil.net_connections(kind='inet6'):
            # 匹配端口（conn.laddr是元组：(ip, port)）
            if conn.laddr and conn.laddr.port == port and conn.pid:
                pids.append(conn.pid)
        
        # 去重
        pids = list(set(pids))
    except psutil.AccessDenied:
        logger.warning("权限不足，无法获取端口占用进程（建议以管理员身份运行）")
    except Exception as e:
        logger.error(f"查找端口占用进程失败：{e}")
    return pids


def kill_process_by_pid(pid: int, force: bool = True) -> bool:
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


def release_port(port: int, force: bool = True) -> bool:
    """
    释放指定端口（杀死所有占用该端口的进程）
    :param port: 目标端口
    :param force: 是否强制结束进程
    :return: True=释放成功，False=释放失败/端口未被占用
    """
    # 1. 检测端口是否被占用
    if not is_port_in_use(port):
        logger.info(f"端口 {port} 未被占用，无需释放")
        return True

    # 2. 查找占用进程
    pids = get_process_id_using_port(port)
    if not pids:
        logger.error(f"端口 {port} 被占用，但无法找到对应的进程PID")
        return False

    # 3. 逐个结束进程
    success = True
    for pid in pids:
        if not kill_process_by_pid(pid, force):
            success = False

    # 4. 验证端口是否释放
    if is_port_in_use(port):
        logger.error(f"端口 {port} 仍被占用（可能有隐藏进程）")
        success = False
    else:
        logger.info(f"端口 {port} 已成功释放")

    return success



def release_port_windows_cmd(port: int) -> bool:
    """
    修复：同时释放IPv4和IPv6端口
    """
    try:
        # 1. 查找所有占用端口的PID（包括IPv6）
        cmd = f'netstat -ano -p tcp | findstr /r /c:":{port} "'
        result = subprocess.check_output(cmd, shell=True, encoding='gbk', errors='ignore').strip()
        if not result:
            # logger.info(f"端口 {port} 未被占用")
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
            except subprocess.CalledProcessError as e:
                # logger.warning(f"释放PID {pid} 失败: {e.stderr.decode('gbk', errors='ignore')}")
                pass
        return True
    except subprocess.CalledProcessError:
        # logger.error(f"端口 {port} 释放失败（权限不足）")
        return False
    except Exception as e:
        logger.error(f"释放端口 {port} 异常: {str(e)}")
        return False

def start_server_safely(port: int = 1234, max_retry: int = 3):
    """
    安全启动服务（自动检测并释放端口）
    :param port: 服务端口
    :param max_retry: 最大重试次数
    """
    retry_count = 0
    while retry_count < max_retry:
        # 检测端口是否可用
        if not is_port_in_use(port):
            logger.info(f"端口 {port} 可用，开始启动服务...")
            # 这里替换为你的服务启动代码
            # 例如：uvicorn.run(app, host="0.0.0.0", port=port)
            return True

        # 端口被占用，尝试释放
        logger.warning(f"端口 {port} 被占用，尝试释放（重试次数：{retry_count + 1}/{max_retry}）")
        if platform.system() == "Windows":
            # Windows优先用cmd方式（备选）
            release_success = release_port_windows_cmd(port) or release_port(port)
        else:
            release_success = release_port(port)

        if release_success:
            retry_count += 1
            continue
        else:
            logger.error(f"端口 {port} 释放失败，启动服务失败")
            return False

    logger.error(f"超出最大重试次数（{max_retry}），端口 {port} 仍被占用")
    return False


# 新增函数1：获取当前主程序自身的PID（核心，解决"怎么知道自己PID"的问题）
def get_self_pid() -> int:
    """
    获取当前运行的Python主程序自身的进程ID（PID）
    :return: 主程序PID（整数）
    """
    self_pid = os.getpid()
    logger.info(f"当前主程序自身PID：{self_pid}")
    return self_pid

# 新增函数2：根据指定PID，查询其占用的所有端口（解决"PID查端口"的核心需求）
def get_ports_by_pid(pid: int, protocol: str = 'tcp') -> list[int]:
    """
    根据PID反向查询该进程占用的所有端口（跨平台，适配端口随机场景）
    :param pid: 目标进程ID（如主程序自身PID）
    :param protocol: 协议类型（tcp/udp，默认tcp，适配99%的服务场景）
    :return: 该PID占用的端口列表（空列表=未占用任何端口）
    """
    try:
        # 初始化端口集合（去重，避免同一端口多次匹配）
        used_ports = set()
        # 遍历系统所有网络连接（仅指定协议）
        for conn in psutil.net_connections(kind=protocol):
            # 过滤条件：连接的PID等于目标PID + 端口有效（非0） + 连接状态为监听/建立中
            if conn.pid == pid and conn.laddr.port != 0:
                used_ports.add(conn.laddr.port)
        # 转列表返回
        port_list = list(used_ports)
        if port_list:
            logger.info(f"PID={pid} 占用的{protocol.upper()}端口：{port_list}")
        else:
            logger.info(f"PID={pid} 未占用任何{protocol.upper()}端口")
        return port_list
    except psutil.AccessDenied:
        logger.error(f"查询PID={pid}的端口失败：无权限（请以管理员/root身份运行程序）")
        return []
    except Exception as e:
        logger.error(f"查询PID={pid}的端口异常：{str(e)}", exc_info=True)
        return []

# 组合函数：主程序自身PID → 查占用端口 → 杀死自身进程（核心入口，适配你的退出流程）
def self_pid_cleanup(force_kill: bool = True) -> tuple[bool, list[int]]:
    """
    主程序自身清理：获取自身PID → 查占用端口 → 杀死自身进程
    :param force_kill: 是否强制杀死自身进程（推荐True，退出流程用）
    :return: (进程杀死是否成功, 自身PID占用的端口列表)
    """
    # 步骤1：获取主程序自身PID（绝对准确）
    self_pid = get_self_pid()
    # 步骤2：查询自身PID占用的所有端口
    self_ports = get_ports_by_pid(self_pid)
    # 步骤3：杀死自身进程（复用你的kill函数）
    kill_success = kill_process_by_pid(self_pid, force_kill)
    # 返回结果：是否杀死成功 + 占用的端口列表（可用于日志/二次校验）
    return kill_success, self_ports



# ========== 使用示例 ==========
if __name__ == "__main__":
    # 目标端口
    TARGET_PORT = 1235

    # 方式1：直接释放端口
    # release_port(TARGET_PORT)

    # 方式2：安全启动服务（自动处理端口占用）
    # start_server_safely(TARGET_PORT)

    # 方式3：Windows下备用方案
    release_port_windows_cmd(TARGET_PORT)
