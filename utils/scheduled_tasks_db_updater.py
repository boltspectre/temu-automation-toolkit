import logging
import os
import sys
from typing import Dict, List, Optional

from loguru import logger

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.classSQLite import SQLiteDB

# 配置日志
logger = logging.getLogger(__name__)


def update_table_structure(
        db,
        table_name: str,
        target_fields: Dict[str, str],
        unique_constraints: Optional[List[str]] = None,
        indexes: Optional[List[str]] = None,
        foreign_keys: Optional[List[str]] = None,
        confirm_drop: bool = True
) -> bool:
    """
    通用化表结构更新函数（支持任意表）
    使用 db.execute_sql 方法执行所有SQL操作

    :param db: SQLiteDB 实例
    :param table_name: 要更新的表名
    :param target_fields: 目标字段结构 {字段名: 字段定义}
                          示例: {"id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT", "name": "TEXT"}
    :param unique_constraints: 唯一约束列表
                          示例: ["UNIQUE (\"uid\" ASC)", "UNIQUE (\"id\" ASC)"]
    :param indexes: 索引SQL列表
                          示例: ['CREATE INDEX IF NOT EXISTS "idx_browser_id" ON "shops" ("browser_id" ASC)']
    :param foreign_keys: 外键约束列表
                          示例: ['FOREIGN KEY ("task_id") REFERENCES task("task_id") ON DELETE CASCADE']
    :param confirm_drop: 是否需要用户确认删除字段操作（True=需要确认，False=自动执行）
    :return: 是否更新成功
    """
    # 设置默认值
    unique_constraints = unique_constraints or []
    indexes = indexes or []
    foreign_keys = foreign_keys or []

    try:
        # ========== 步骤1：检查表是否存在 ==========
        table_exists = db.table_exists(table_name)

        if not table_exists:
            # ========== 步骤2：表不存在 - 直接创建完整表 ==========
            logger.info(f"⚠️ {table_name} 表不存在，开始创建新表")

            # 构建创建表的SQL
            fields_sql = [f'"{field}" {definition}' for field, definition in target_fields.items()]

            create_sql = f'''
            CREATE TABLE "{table_name}" (
              {", ".join(fields_sql)}
              {", " + ", ".join(unique_constraints) if unique_constraints else ""}
              {", " + ", ".join(foreign_keys) if foreign_keys else ""}
            )
            '''
            # 执行创建表SQL
            db.execute_sql(create_sql, commit=True)
            logger.info(f"✅ 成功创建 {table_name} 表")

            # 创建索引
            for index_sql in indexes:
                db.execute_sql(index_sql, commit=True)
                logger.info(f"✅ 成功创建索引: {index_sql[:50]}...")
            return True

        # ========== 步骤3：表已存在 - 获取当前结构并对比 ==========
        # 获取当前表结构
        current_fields: Dict[str, str] = {}
        table_info = db.get_table_info(table_name)
        for col in table_info:
            current_fields[col["name"]] = col["type"]

        # 检查是否有需要删除的字段（高风险操作）
        fields_to_drop = [f for f in current_fields if f not in target_fields]
        if fields_to_drop:
            # 提示数据丢失风险
            logger.error(f"\n❌ 检测到 {table_name} 表需要删除的字段（会导致数据丢失）：{fields_to_drop}")
            logger.warning(f"⚠️ SQLite 不支持直接删除字段，需重建 {table_name} 表！")

            # 判断是否需要用户确认
            if confirm_drop:
                confirm = input(f"👉 确认继续？删除后这些字段的数据将永久丢失 (y/N): ").strip().lower()
                if confirm != 'y':
                    logger.info(f"❌ 用户取消操作，{table_name} 表结构更新终止")
                    return False
            else:
                logger.info(f"⚠️ 自动执行删除字段操作（confirm_drop=False）")

            # ========== 风险操作：重建表（保留有效字段） ==========
            logger.info(f"📝 开始重建 {table_name} 表（保留有效字段）")

            # 1. 重命名原表为临时表
            temp_table_name = f"{table_name}_temp"
            db.execute_sql(f"ALTER TABLE {table_name} RENAME TO {temp_table_name}", commit=True)
            logger.info(f"✅ 原表已重命名为 {temp_table_name}")

            # 2. 创建新表（目标结构）
            fields_sql = [f'"{field}" {definition}' for field, definition in target_fields.items()]
            create_new_sql = f'''
            CREATE TABLE "{table_name}" (
              {", ".join(fields_sql)}
              {", " + ", ".join(unique_constraints) if unique_constraints else ""}
              {", " + ", ".join(foreign_keys) if foreign_keys else ""}
            )
            '''
            db.execute_sql(create_new_sql, commit=True)
            logger.info(f"✅ 已创建新的 {table_name} 表")

            # 3. 迁移数据（只迁移目标表包含的字段）
            keep_fields = [f for f in current_fields if f in target_fields]
            if keep_fields:
                fields_str = ", ".join([f'"{f}"' for f in keep_fields])
                insert_sql = f'INSERT INTO {table_name} ({fields_str}) SELECT {fields_str} FROM {temp_table_name}'
                db.execute_sql(insert_sql, commit=True)
                logger.info(f"✅ 已迁移 {len(keep_fields)} 个字段的数据")

            # 4. 删除临时表
            db.execute_sql(f"DROP TABLE {temp_table_name}", commit=True)
            logger.info(f"✅ 已删除临时表 {temp_table_name}")

        else:
            # ========== 无删列风险 - 仅新增缺失字段 ==========
            # 检查需要新增的字段
            fields_to_add = [f for f in target_fields if f not in current_fields]

            if fields_to_add:
                for field in fields_to_add:
                    # 提取字段类型（兼容复杂定义，如 "TEXT NOT NULL DEFAULT 'xxx'"）
                    field_type = target_fields[field].split()[0]
                    add_sql = f'ALTER TABLE {table_name} ADD COLUMN "{field}" {field_type}'
                    db.execute_sql(add_sql, commit=True)
                    logger.info(f"✅ 新增字段：{field} ({field_type})")
            else:
                logger.info(f"ℹ️ {table_name} 表字段已为最新，无需新增")

        # ========== 步骤4：确保索引存在 ==========
        for index_sql in indexes:
            db.execute_sql(index_sql, commit=True)
        logger.info(f"✅ {table_name} 表所有索引已确保存在")

        # ========== 验证最终结构 ==========
        final_fields = [col["name"] for col in db.get_table_info(table_name)]
        logger.info(f"\n🎉 {table_name} 表结构更新完成！最终字段列表：")
        logger.info(f"字段列表：{final_fields}")

        return True

    except Exception as e:
        logger.error(f"\n❌ {table_name} 表结构更新失败：{str(e)}", exc_info=True)
        return False


def create_scheduled_tasks_table(db):
    """创建 scheduled_tasks 表"""
    SCHEDULED_TASKS_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "task_id": "TEXT NOT NULL",
        "schedule_type": "TEXT NOT NULL",
        "schedule_time": "TEXT",
        "schedule_interval": "INTEGER",
        "schedule_enabled": "INTEGER DEFAULT 1",
        "schedule_next_run": "TEXT",
        "last_run_time": "TEXT",
        "run_count": "INTEGER DEFAULT 0",
        "max_run_count": "INTEGER",
        "created_time": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "updated_time": "DATETIME DEFAULT CURRENT_TIMESTAMP"
    }
    
    SCHEDULED_TASKS_FOREIGN_KEYS = []
    
    SCHEDULED_TASKS_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_task_id" ON "scheduled_tasks" ("task_id" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_schedule_next_run" ON "scheduled_tasks" ("schedule_next_run" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_schedule_enabled" ON "scheduled_tasks" ("schedule_enabled" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="scheduled_tasks",
        target_fields=SCHEDULED_TASKS_TARGET_FIELDS,
        foreign_keys=SCHEDULED_TASKS_FOREIGN_KEYS,
        indexes=SCHEDULED_TASKS_INDEXES,
        confirm_drop=False
    )


def update_scheduled_tasks_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 scheduled_tasks 表结构"""
    SCHEDULED_TASKS_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "task_id": "TEXT NOT NULL",
        "schedule_type": "TEXT NOT NULL",
        "schedule_time": "TEXT",
        "schedule_interval": "INTEGER",
        "schedule_enabled": "INTEGER DEFAULT 1",
        "schedule_next_run": "TEXT",
        "last_run_time": "TEXT",
        "run_count": "INTEGER DEFAULT 0",
        "max_run_count": "INTEGER",
        "created_time": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "updated_time": "DATETIME DEFAULT CURRENT_TIMESTAMP"
    }
    
    SCHEDULED_TASKS_FOREIGN_KEYS = []
    
    SCHEDULED_TASKS_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_task_id" ON "scheduled_tasks" ("task_id" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_schedule_next_run" ON "scheduled_tasks" ("schedule_next_run" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_schedule_enabled" ON "scheduled_tasks" ("schedule_enabled" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="scheduled_tasks",
        target_fields=SCHEDULED_TASKS_TARGET_FIELDS,
        foreign_keys=SCHEDULED_TASKS_FOREIGN_KEYS,
        indexes=SCHEDULED_TASKS_INDEXES,
        confirm_drop=confirm_drop
    )


def initialize_scheduled_tasks_database():
    """
    检测并初始化 scheduled_tasks 表
    """
    try:
        from config.common_config import db
        
        # 检查表是否存在
        table_exists = db.table_exists("scheduled_tasks")
        
        if not table_exists:
            logger.info("检测到首次运行，开始创建 scheduled_tasks 表")
            success = create_scheduled_tasks_table(db)
            
            if success:
                logger.info("✅ scheduled_tasks 表创建成功")
                return True
            else:
                logger.error("❌ scheduled_tasks 表创建失败")
                return False
        else:
            # 检查表结构，如果不存在则创建
            logger.info("scheduled_tasks 表已存在，检查表结构")
            
            # 检查是否需要重建表（移除外键约束）
            # 通过查询表的CREATE SQL语句来检查是否有外键约束
            table_sql = db.execute_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='scheduled_tasks'",
                fetch="fetch_one"
            )
            
            has_foreign_key = False
            if table_sql and table_sql.get("sql"):
                create_sql = table_sql["sql"].upper()
                if "FOREIGN KEY" in create_sql or "REFERENCES" in create_sql:
                    has_foreign_key = True
                    logger.info("检测到 scheduled_tasks 表存在外键约束，需要重建表")
            
            # 更新表结构（如果有外键约束会自动重建）
            success = update_scheduled_tasks_table_structure(db, confirm_drop=False)
            
            if success:
                logger.info("✅ scheduled_tasks 表结构检查完成")
                return True
            else:
                logger.error("❌ scheduled_tasks 表结构检查失败")
                return False
                
    except Exception as e:
        logger.error(f"scheduled_tasks 表初始化异常: {e}")
        return False


# ==================== 使用示例 ====================
if __name__ == "__main__":
    print("=== 初始化 scheduled_tasks 表 ===")
    success = initialize_scheduled_tasks_database()
    if success:
        print("✅ scheduled_tasks 表初始化成功")
    else:
        print("❌ scheduled_tasks 表初始化失败")