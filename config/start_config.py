# main.py
import sys
import os
import time
import traceback
from datetime import datetime

import urllib3
from PyQt5.QtWidgets import QMessageBox
from loguru import logger

from config.middleware_config import (
    max_concurrent_tasks
)
from utils.multiThreading_manager import MainTaskManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 启动主任务管理器
MAIN_TASK_MANAGER = MainTaskManager(
    max_concurrent_tasks=max_concurrent_tasks,
    task_timeout=3000000
)
MAIN_TASK_MANAGER.start()


# ====== 全局异常捕获（保留）======
def handle_exception(exc_type, exc_value, exc_traceback):
    """捕获所有未处理异常并写入日志文件"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 允许 Ctrl+C 正常退出
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # 关键：在写入 error.log 之前，先安全关闭数据库并合并 WAL 文件
    try:
        from config.common_config import db
        db.close_safely()
    except:
        pass

    # 获取错误日志记录次数配置
    try:
        from config.common_config import config_manager
        max_error_logs = int(config_manager.get_or_set_config("max_error_logs", "100"))
    except:
        max_error_logs = 100  # 默认值

    # 创建error文件夹
    error_dir = "error"
    if not os.path.exists(error_dir):
        os.makedirs(error_dir)

    log_file = os.path.join(error_dir, "error.log")
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 专门的分隔符，用于分隔每次错误记录
    separator = "=" * 60
    log_entry = f"[{timestamp}] 全局异常:\n{error_msg}\n"
    
    # 检查error.log是否存在以及记录次数
    error_count = 0
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                # 通过分隔符计算错误次数
                error_count = content.count(separator)
        except:
            error_count = 0
    
    # 如果超过最大记录次数，进行日志轮转
    if error_count >= max_error_logs:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 分割日志条目
            entries = content.split(separator)
            if entries and entries[0]:  # 确保有内容
                # 保留最后20%的日志条目
                keep_count = max(1, int(len(entries) * 0.2))
                recent_entries = entries[-keep_count:]
                
                # 重新构建日志内容
                new_content = separator.join(recent_entries)
                
                # 将保留的内容放在前面，弥补删除的空白区域
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(new_content + "\n" + separator + "\n" + log_entry)
        except Exception as e:
            # 如果轮转失败，直接追加
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n" + separator + "\n" + log_entry)
    else:
        # 正常追加日志
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n" + separator + "\n" + log_entry)

    # 弹窗提示用户
    QMessageBox.critical(None, "程序发生错误", f"发生未处理异常，请查看 error.log 文件。\n\n{str(exc_value)}")


# 设置全局异常钩子
sys.excepthook = handle_exception


def check_error_log_on_startup():
    """程序启动时检查error.log文件并处理日志轮转"""
    try:
        from config.common_config import config_manager
        max_error_logs = int(config_manager.get_or_set_config("max_error_logs", "100"))
    except:
        max_error_logs = 100  # 默认值

    # 创建error文件夹
    error_dir = "error"
    if not os.path.exists(error_dir):
        os.makedirs(error_dir)

    log_file = os.path.join(error_dir, "error.log")
    separator = "=" * 60
    
    # 检查error.log是否存在以及记录次数
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                # 通过分隔符计算错误次数
                error_count = content.count(separator)
            
            # 如果超过最大记录次数，进行日志轮转
            if error_count > max_error_logs:
                # 分割日志条目
                entries = content.split(separator)
                if entries and entries[0]:  # 确保有内容
                    # 保留最后20%的日志条目
                    keep_count = max(1, int(len(entries) * 0.2))
                    recent_entries = entries[-keep_count:]
                    
                    # 重新构建日志内容
                new_content = separator.join(recent_entries)
                
                # 将保留的内容放在前面，弥补删除的空白区域
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
        except Exception as e:
            # 如果处理失败，静默处理
            pass


# 程序启动时检查错误日志
check_error_log_on_startup()



# import schedule
#
# # 配置定时任务：每5分钟自动检测并清理无效浏览器
# schedule.every(5).minutes.do(auto_detect_and_clean_all_browsers)