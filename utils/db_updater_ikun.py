import logging
from typing import Dict, List, Optional, Any

from config.common_config import db

# 配置日志
logger = logging.getLogger(__name__)


def update_table_structure(
        db,
        table_name: str,
        target_fields: Dict[str, str],
        unique_constraints: Optional[List[str]] = None,
        indexes: Optional[List[str]] = None,
        confirm_drop: bool = True  # 是否需要用户确认删除字段
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
    :param confirm_drop: 是否需要用户确认删除字段操作（True=需要确认，False=自动执行）
    :return: 是否更新成功
    """
    # 设置默认值
    unique_constraints = unique_constraints or []
    indexes = indexes or []

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


# ==================== 针对 shops 表的快捷调用函数（兼容原有逻辑） ====================
def update_shops_table_structure(db, confirm_drop: bool = True) -> bool:
    """
    升级 shops 表结构（新增 multi_shops 和 remarks 字段）
    这是通用函数的快捷调用，无需修改即可使用
    """
    # shops 表目标结构
    SHOP_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "shop_name": "TEXT",
        "shop_abbr": "TEXT",
        "phone": "TEXT",
        "password": "TEXT",
        "browser_id": "TEXT",
        "connect_status": "TEXT NOT NULL DEFAULT '未连接'",
        "create_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "update_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "headers": "TEXT",
        "cookies": "TEXT",
        "cookies_us": "TEXT",  # 新增：美区 cookies
        "cookies_eu": "TEXT",  # 新增：欧区 cookies
        "uid": "text",
        "mall_id": "INTEGER",
        "is_multi_shops": "TEXT",  # 新增字段
        "remarks": "TEXT"  # 新增字段
    }

    # 唯一约束
    SHOP_UNIQUE_CONSTRAINTS = [
        "UNIQUE (\"uid\" ASC)",
        "UNIQUE (\"id\" ASC)"
    ]

    # 索引配置
    SHOP_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_browser_id" ON "shops" ("browser_id" ASC)'
    ]

    # 调用通用更新函数
    return update_table_structure(
        db=db,
        table_name="shops",
        target_fields=SHOP_TARGET_FIELDS,
        unique_constraints=SHOP_UNIQUE_CONSTRAINTS,
        indexes=SHOP_INDEXES,
        confirm_drop=confirm_drop
    )

# ==================== 针对 task 表的快捷调用函数（适配指定表结构） ====================
def update_task_table_structure(db, confirm_drop: bool = True) -> bool:
    """
    升级/创建 task 表结构（完全匹配指定的数据库表定义）
    通用函数的快捷调用，无需修改即可使用
    """
    # task 表目标结构（与你提供的CREATE TABLE完全一致）
    TASK_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "task_name": "TEXT",
        "task_id": "TEXT NOT NULL",
        "status": "TEXT",
        "msg": "TEXT",
        "remarks": "TEXT",
        "task_group": "TEXT",
        "func_name": "TEXT",
        "mall_id": "INTEGER",
        "task_kwargs": "TEXT",
        "is_main_task": "INTEGER DEFAULT 0",
        "is_maintain_task": "INTEGER DEFAULT 0",
        "auto_rerun_time": "TEXT",
        "parent_task_id": "TEXT",
        "log": "TEXT",
        "create_time": "DATETIME DEFAULT (datetime('now', '+8 hours'))",
        "update_time": "DATETIME DEFAULT (datetime('now', '+8 hours'))",
        "func_path": "TEXT",
        "ip": "TEXT"
    }

    # 唯一约束（匹配 UNIQUE ("task_id" ASC)）
    TASK_UNIQUE_CONSTRAINTS = [
        "UNIQUE (\"task_id\" ASC)"
    ]

    # 索引配置（匹配所有CREATE INDEX，均加 IF NOT EXISTS 防止重复创建）
    TASK_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_parent_task" ON "task" ("parent_task_id" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_status" ON "task" ("status" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_group" ON "task" ("task_group" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_main" ON "task" ("is_main_task" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_parent" ON "task" ("parent_task_id" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_status" ON "task" ("status" ASC)'
    ]

    # 调用通用更新函数完成task表结构更新
    return update_table_structure(
        db=db,
        table_name="task",
        target_fields=TASK_TARGET_FIELDS,
        unique_constraints=TASK_UNIQUE_CONSTRAINTS,
        indexes=TASK_INDEXES,
        confirm_drop=confirm_drop
    )



# ==================== 扩展工具函数（通用化） ====================
def batch_update_table_data(
        db,
        table_name: str,
        update_data: List[Dict],
        update_fields: List[str],
        where_field: str = "id",
        update_time_field: Optional[str] = None
) -> int:
    """
    通用批量更新表数据函数
    :param db: SQLiteDB 实例
    :param table_name: 表名
    :param update_data: 更新数据列表 [{"field1": val1, where_field: val}, ...]
    :param update_fields: 要更新的字段列表
    :param where_field: 条件字段（如 "shop_abbr", "id"）
    :param update_time_field: 更新时间字段（如 "update_time"）
    :return: 成功更新的行数
    """
    if not update_data or not update_fields:
        return 0

    # 构建更新SQL
    set_clauses = [f"{field} = ?" for field in update_fields]
    if update_time_field:
        set_clauses.append(f"{update_time_field} = datetime('now', '+8 hours')")

    update_sql = f"""
    UPDATE {table_name} 
    SET {", ".join(set_clauses)}
    WHERE {where_field} = ?
    """

    success_count = 0
    for data in update_data:
        try:
            # 构建参数（更新字段值 + 条件值）
            params = [data.get(field) for field in update_fields]
            if update_time_field:
                params.append(None)  # update_time 由SQL函数生成，无需传参
            params.append(data.get(where_field))

            affected_rows = db.execute_sql(update_sql, params, commit=True)
            if affected_rows > 0:
                success_count += 1
        except Exception as e:
            logger.error(f"更新 {table_name} 表中 {where_field}={data.get(where_field)} 失败：{e}")

    return success_count


def get_record_by_field(
        db,
        table_name: str,
        field_name: str,
        field_value: Any,
        fields: Optional[List[str]] = None
) -> Optional[Dict]:
    """
    通用根据字段查询单条记录函数
    :param db: SQLiteDB 实例
    :param table_name: 表名
    :param field_name: 查询字段名
    :param field_value: 查询字段值
    :param fields: 要查询的字段列表（None=查询所有）
    :return: 记录字典
    """
    select_fields = "*" if not fields else ", ".join(fields)
    sql = f"SELECT {select_fields} FROM {table_name} WHERE {field_name} = ? LIMIT 1"
    result = db.execute_sql(sql, (field_value,), fetch="fetch_one")
    return result


# ==================== 数据库初始化函数 ====================
def initialize_database():
    """
    检测并初始化数据库
    如果是第一次运行或数据库不存在，则创建所有必要的表结构
    """
    try:
        # 检查数据库文件是否存在
        from config.common_config import db
        from modules.classSQLite import load_db_config
        import os
        
        # 获取数据库路径
        config = load_db_config("./配置文件_系统配置/db_config.json")
        db_path = config.get("db_path", ":memory:")
        
        # 如果是内存数据库，跳过检查
        if db_path == ":memory:":
            logger.info("使用内存数据库，跳过初始化检查")
            return True
            
        # 检查数据库文件是否存在
        db_exists = os.path.exists(db_path)
        
        if not db_exists:
            logger.info("检测到首次运行，开始初始化数据库结构")
            
            # 创建所有必要的表
            success = True
            
            # 1. 创建 config 表
            success &= create_config_table(db)
            
            # 2. 创建 record 表
            success &= create_record_table(db)
            
            # 3. 创建 shops 表
            success &= create_shops_table(db)
            
            # 4. 创建 task 表
            success &= create_task_table(db)
            
            if success:
                logger.info("✅ 数据库初始化完成")
                return True
            else:
                logger.error("❌ 数据库初始化失败")
                return False
        else:
            # 检查表是否存在，如果不存在则创建
            logger.info("数据库文件已存在，检查表结构")
            
            # 检查并更新所有表结构
            success = True
            success &= update_config_table_structure(db, confirm_drop=False)
            success &= update_record_table_structure(db, confirm_drop=False)
            success &= update_shops_table_structure(db, confirm_drop=False)
            success &= update_task_table_structure(db, confirm_drop=False)
            
            if success:
                logger.info("✅ 数据库表结构检查完成")
                return True
            else:
                logger.error("❌ 数据库表结构检查失败")
                return False
                
    except Exception as e:
        logger.error(f"数据库初始化异常: {e}")
        return False


def create_config_table(db):
    """创建 config 表"""
    CONFIG_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "key": "TEXT NOT NULL",
        "value": "TEXT",
        "create_time": "DATE",
        "update_time": "DATE",
        "is_deleted": "integer"
    }
    
    CONFIG_UNIQUE_CONSTRAINTS = [
        "UNIQUE (\"key\" ASC)"
    ]
    
    return update_table_structure(
        db=db,
        table_name="config",
        target_fields=CONFIG_TARGET_FIELDS,
        unique_constraints=CONFIG_UNIQUE_CONSTRAINTS,
        confirm_drop=False
    )


def create_record_table(db):
    """创建 record 表"""
    RECORD_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "uid": "text",
        "upload_pic_all": "text",
        "create_time": "DATE",
        "update_time": "DATE"
    }
    
    return update_table_structure(
        db=db,
        table_name="record",
        target_fields=RECORD_TARGET_FIELDS,
        confirm_drop=False
    )


def create_shops_table(db):
    """创建 shops 表"""
    SHOP_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "shop_name": "TEXT",
        "shop_abbr": "TEXT",
        "phone": "TEXT",
        "password": "TEXT",
        "browser_id": "TEXT",
        "connect_status": "TEXT NOT NULL DEFAULT '未连接'",
        "create_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "update_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "headers": "TEXT",
        "cookies": "TEXT",
        "cookies_us": "TEXT",  # 新增：美区 cookies
        "cookies_eu": "TEXT",  # 新增：欧区 cookies
        "uid": "text",
        "mall_id": "INTEGER",
        "is_multi_shops": "TEXT",
        "remarks": "TEXT"
    }
    
    SHOP_UNIQUE_CONSTRAINTS = [
        "UNIQUE (\"uid\" ASC)",
        "UNIQUE (\"id\" ASC)"
    ]
    
    SHOP_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_browser_id" ON "shops" ("browser_id" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="shops",
        target_fields=SHOP_TARGET_FIELDS,
        unique_constraints=SHOP_UNIQUE_CONSTRAINTS,
        indexes=SHOP_INDEXES,
        confirm_drop=False
    )


def create_task_table(db):
    """创建 task 表"""
    TASK_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "task_name": "TEXT",
        "task_id": "TEXT NOT NULL",
        "status": "TEXT",
        "msg": "TEXT",
        "remarks": "TEXT",
        "task_group": "TEXT",
        "func_name": "TEXT",
        "mall_id": "INTEGER",
        "task_kwargs": "TEXT",
        "is_main_task": "INTEGER DEFAULT 0",
        "is_maintain_task": "INTEGER DEFAULT 0",
        "auto_rerun_time": "TEXT",
        "parent_task_id": "TEXT",
        "log": "TEXT",
        "create_time": "DATETIME DEFAULT (datetime('now', '+8 hours'))",
        "update_time": "DATETIME DEFAULT (datetime('now', '+8 hours'))",
        "func_path": "TEXT",
        "ip": "TEXT"
    }
    
    TASK_UNIQUE_CONSTRAINTS = [
        "UNIQUE (\"task_id\" ASC)"
    ]
    
    TASK_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_parent_task" ON "task" ("parent_task_id" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_status" ON "task" ("status" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_group" ON "task" ("task_group" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_main" ON "task" ("is_main_task" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_parent" ON "task" ("parent_task_id" ASC)',
        'CREATE INDEX IF NOT EXISTS "idx_task_status" ON "task" ("status" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="task",
        target_fields=TASK_TARGET_FIELDS,
        unique_constraints=TASK_UNIQUE_CONSTRAINTS,
        indexes=TASK_INDEXES,
        confirm_drop=False
    )


def update_config_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 config 表结构"""
    CONFIG_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "key": "TEXT NOT NULL",
        "value": "TEXT",
        "create_time": "DATE",
        "update_time": "DATE",
        "is_deleted": "integer"
    }
    
    CONFIG_UNIQUE_CONSTRAINTS = [
        "UNIQUE (\"key\" ASC)"
    ]
    
    return update_table_structure(
        db=db,
        table_name="config",
        target_fields=CONFIG_TARGET_FIELDS,
        unique_constraints=CONFIG_UNIQUE_CONSTRAINTS,
        confirm_drop=confirm_drop
    )


def update_record_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 record 表结构"""
    RECORD_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "uid": "text",
        "upload_pic_all": "text",
        "create_time": "DATE",
        "update_time": "DATE"
    }
    
    return update_table_structure(
        db=db,
        table_name="record",
        target_fields=RECORD_TARGET_FIELDS,
        confirm_drop=confirm_drop
    )


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 示例1：更新 shops 表（原有逻辑，快捷调用）
    print("=== 示例1：更新 shops 表 ===")
    update_success = update_shops_table_structure(db)
    if update_success:
        print("✅ shops 表结构更新成功")

    update_success = update_task_table_structure(db)
    if update_success:
        print("✅ shops 表结构更新成功")

    exit(1)

    # 示例2：自定义其他表结构（比如创建/更新 users 表）
    print("\n=== 示例2：自定义更新 users 表 ===")
    # 定义 users 表目标结构
    USER_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "username": "TEXT UNIQUE NOT NULL",
        "email": "TEXT",
        "age": "INTEGER",
        "address": "TEXT",  # 新增字段
        "create_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    }

    # 定义唯一约束和索引
    USER_UNIQUE_CONSTRAINTS = ["UNIQUE (\"username\" ASC)"]
    USER_INDEXES = [
        'CREATE INDEX IF NOT EXISTS "idx_user_email" ON "users" ("email" ASC)'
    ]

    # 调用通用函数更新 users 表
    user_update_success = update_table_structure(
        db=db,
        table_name="users",
        target_fields=USER_TARGET_FIELDS,
        unique_constraints=USER_UNIQUE_CONSTRAINTS,
        indexes=USER_INDEXES,
        confirm_drop=True
    )
    if user_update_success:
        # print("✅ users 表结构更新成功")

        # 插入测试用户
        test_user = {
            "username": "test_user_001",
            "email": "test@example.com",
            "age": 25,
            "address": "北京市海淀区"
        }
        insert_sql = """
                     INSERT INTO users (username, email, age, address)
                     VALUES (?, ?, ?, ?) \
                     """
        params = (test_user["username"], test_user["email"], test_user["age"], test_user["address"])
        user_id = db.execute_sql(insert_sql, params, fetch="none")
        print(f"✅ 插入测试用户，ID: {user_id}")

        # 通用查询函数使用
        user_info = get_record_by_field(db, "users", "username", "test_user_001")
        if user_info:
            print(f"✅ 查询到用户信息：{user_info}")

        # 通用批量更新函数使用
        update_data = [
            {"username": "test_user_001", "age": 26, "address": "北京市朝阳区"}
        ]
        updated_count = batch_update_table_data(
            db=db,
            table_name="users",
            update_data=update_data,
            update_fields=["age", "address"],
            where_field="username",
            update_time_field=None
        )
        print(f"✅ 批量更新完成，更新行数：{updated_count}")