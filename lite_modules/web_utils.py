"""
网页打开工具模块
提供通用的打开网页功能，支持跨平台使用
"""

import webbrowser
import platform
import logging

# 设置日志
logger = logging.getLogger(__name__)


def open_url_in_browser_core(url):
    """
    通用的核心打开网页函数
    :param url: 要打开的URL
    :return: bool - 是否成功打开浏览器
    """
    if not url:
        logger.error("URL为空，无法打开")
        return False
        
    # 确保URL包含协议
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    try:
        # 方案1：优先使用系统默认浏览器（跨平台兼容）
        # open_new_tab 会在新标签页打开（推荐），open 会打开新窗口
        success = webbrowser.open_new_tab(url)

        if not success:
            # 方案2：兼容处理（针对部分系统 webbrowser 可能返回 False 的情况）
            os_type = platform.system()
            if os_type == "Windows":
                import os
                os.startfile(url)  # Windows 专属方式
            elif os_type == "Darwin":  # macOS
                import subprocess
                subprocess.run(["open", url], check=True, capture_output=True)
            elif os_type == "Linux":  # Linux
                import subprocess
                subprocess.run(["xdg-open", url], check=True, capture_output=True)
            success = True

        if not success:
            logger.error(f"无法打开默认浏览器访问: {url}")
            return False
            
        logger.info(f"成功打开浏览器访问: {url}")
        return True

    except Exception as e:
        logger.error(f"打开网页失败 | URL: {url} | 异常: {str(e)}", exc_info=True)
        return False