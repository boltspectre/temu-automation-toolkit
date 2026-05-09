# 配置文件_系统配置/middleware_config.py
from config.common_config import (
    db, config_manager, generator,
    max_concurrent_tasks, modify_price_concurrent, upload_real_pic_concurrent, hupu_post_list_concurrent, hupu_detail_list_concurrent, hupu_score_list_concurrent,
    task_concurrent_config, get_current_time
)

# 这里只导出变量，不初始化任务管理器，避免循环导入
__all__ = [
    "db", "config_manager", "generator",
    "max_concurrent_tasks", "modify_price_concurrent", "upload_real_pic_concurrent", "hupu_post_list_concurrent", "hupu_detail_list_concurrent", "hupu_score_list_concurrent",
    "task_concurrent_config", "get_current_time"
]