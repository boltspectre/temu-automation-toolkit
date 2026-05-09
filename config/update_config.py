import os

from config.common_config import db
# 更细配置
from utils.db_updater_ikun import update_shops_table_structure, update_task_table_structure

def software_update_config():
    root_dir = os.path.abspath(os.path.dirname(__file__))
    # 拼接lock.txt的完整路径
    lock_file_path = os.path.join(root_dir, "lock.txt")

    # 检查文件是否存在，不存在则创建
    if not os.path.exists(lock_file_path):
        # 以写入模式创建空文件（若需写入内容，可在open内添加，如write("lock flag")）
        with open(lock_file_path, "w", encoding="utf-8") as f:
            pass  # 仅创建空文件，无内容写入
        update_success = update_shops_table_structure(db)
        if update_success:
            print("✅ 表结构更新成功")

        update_success = update_task_table_structure(db)
        if update_success:
            print("✅ 表结构更新成功")