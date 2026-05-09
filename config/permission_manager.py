# config/permission_manager.py
"""
统一权限管理工具
提供权限的保存、读取和检查功能
权限保存在数据库中
"""

import json
from loguru import logger


class PermissionManager:
    """权限管理器 - 权限保存在数据库中"""

    @staticmethod
    def save_permissions(permissions, kami: str = None):
        """
        保存权限到数据库

        Args:
            permissions: 权限列表，如 ["temu", "caiwu"]
            kami: 当前卡密（已废弃，保留兼容性）
        """
        try:
            from config.common_config import db

            # 将权限列表转换为JSON字符串
            permissions_json = json.dumps(permissions)

            # 检查是否已存在权限记录
            result = db.execute_sql(
                "SELECT id FROM config WHERE key = 'permissions' AND is_deleted = 0",
                fetch="fetch_one"
            )

            if result:
                # 更新现有记录
                db.execute_sql(
                    "UPDATE config SET value = ?, update_time = datetime('now') WHERE key = 'permissions'",
                    (permissions_json,),
                    commit=True
                )
                logger.info(f"权限已更新到数据库: {permissions}")
            else:
                # 插入新记录
                db.execute_sql(
                    "INSERT INTO config (key, value, create_time, update_time, is_deleted) VALUES (?, ?, datetime('now'), datetime('now'), 0)",
                    ("permissions", permissions_json),
                    commit=True
                )
                logger.info(f"权限已保存到数据库: {permissions}")
            return True
        except Exception as e:
            logger.error(f"权限保存失败: {str(e)}")
            return False

    @staticmethod
    def load_permissions(kami: str = None):
        """
        从数据库读取权限

        Args:
            kami: 当前卡密（已废弃，保留兼容性）

        Returns:
            list: 权限列表，如 ["temu", "caiwu"]
        """
        try:
            from config.common_config import db

            # 从数据库读取权限
            result = db.execute_sql(
                "SELECT value FROM config WHERE key = 'permissions' AND is_deleted = 0",
                fetch="fetch_one"
            )

            if result and result.get("value"):
                permissions = json.loads(result["value"])
                # logger.info(f"从数据库加载权限: {permissions}")

                return permissions

            logger.warning("数据库中未找到权限配置，返回空权限列表")
            return []
        except Exception as e:
            logger.warning(f"数据库未初始化或权限加载失败: {str(e)}")
            return []

    @staticmethod
    def clear_permissions():
        """
        清除数据库中的权限（用于退出登录）
        """
        try:
            from config.common_config import db

            db.execute_sql(
                "UPDATE config SET is_deleted = 1, update_time = datetime('now') WHERE key = 'permissions'",
                commit=True
            )
            logger.info("数据库中的权限已清除")
        except Exception as e:
            logger.error(f"清除权限失败: {str(e)}")

    @staticmethod
    def check_permission(task_type, permissions=None, kami: str = None):
        """
        检查是否有执行指定任务类型的权限

        Args:
            task_type: 任务类型（支持数字编码或中文名称）
            permissions: 权限列表，如果为None则从数据库加载
            kami: 当前卡密（已废弃，保留兼容性）

        Returns:
            bool: 是否有权限
        """
        if permissions is None:
            permissions = PermissionManager.load_permissions()

        from config.task_permission_config import check_task_permission
        return check_task_permission(task_type, permissions)


from config.kami_config import kami_config
permission_manager = PermissionManager()