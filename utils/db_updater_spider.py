import logging
import os
from typing import Dict, List, Optional, Any

from loguru import logger
from modules.classSQLite import SQLiteDB

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


def initialize_hupu_database():
    """
    检测并初始化 hupu 数据库
    如果是第一次运行或数据库不存在，则创建所有必要的表结构
    """
    try:
        # 获取 hupu 数据库路径
        hupu_db_path = "./配置文件_系统配置/hupu.db"
        
        # 检查数据库文件是否存在
        db_exists = os.path.exists(hupu_db_path)
        
        # 创建临时配置文件
        import json
        temp_config_path = "./配置文件_系统配置/hupu_db_config.json"
        with open(temp_config_path, "w", encoding="utf-8") as f:
            json.dump({"db_path": hupu_db_path}, f)
        
        # 创建 hupu 数据库连接
        hupu_db = SQLiteDB(temp_config_path, debug=True)
        
        if not db_exists:
            logger.info("检测到首次运行，开始初始化 hupu 数据库结构")
            
            # 创建所有必要的表
            success = True
            
            # 1. 创建 hupu_detail_list 表
            success &= create_hupu_detail_list_table(hupu_db)
            
            # 2. 创建 ai_analysis 表
            success &= create_ai_analysis_table(hupu_db)
            
            # 3. 创建 hupu_post_list 表
            success &= create_hupu_post_list_table(hupu_db)
            
            # 4. 创建 hupu_score_list 表
            success &= create_hupu_score_list_table(hupu_db)
            
            if success:
                logger.info("✅ hupu 数据库初始化完成")
                hupu_db.close()
                # 删除临时配置文件
                try:
                    os.remove(temp_config_path)
                except:
                    pass
                return True
            else:
                logger.error("❌ hupu 数据库初始化失败")
                hupu_db.close()
                # 删除临时配置文件
                try:
                    os.remove(temp_config_path)
                except:
                    pass
                return False
        else:
            # 检查表是否存在，如果不存在则创建
            logger.info("hupu 数据库文件已存在，检查表结构")
            
            # 检查并更新所有表结构
            success = True
            success &= update_hupu_detail_list_table_structure(hupu_db, confirm_drop=False)
            success &= update_ai_analysis_table_structure(hupu_db, confirm_drop=False)
            success &= update_hupu_post_list_table_structure(hupu_db, confirm_drop=False)
            success &= update_hupu_score_list_table_structure(hupu_db, confirm_drop=False)
            
            if success:
                logger.info("✅ hupu 数据库表结构检查完成")
                hupu_db.close()
                # 删除临时配置文件
                try:
                    os.remove(temp_config_path)
                except:
                    pass
                return True
            else:
                logger.error("❌ hupu 数据库表结构检查失败")
                hupu_db.close()
                # 删除临时配置文件
                try:
                    os.remove(temp_config_path)
                except:
                    pass
                return False
                
    except Exception as e:
        logger.error(f"hupu 数据库初始化异常: {e}")
        return False


def create_ai_analysis_table(db):
    """创建 ai_analysis 表"""
    AI_ANALYSIS_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "task_name": "TEXT",
        "status": "TEXT",
        "msg": "TEXT",
        "remarks": "TEXT",
        "task_id": "TEXT",
        "type": "TEXT",
        "ai_sumup": "TEXT"
    }
    
    return update_table_structure(
        db=db,
        table_name="ai_analysis",
        target_fields=AI_ANALYSIS_TARGET_FIELDS,
        confirm_drop=False
    )


def create_hupu_post_list_table(db):
    """创建 hupu_post_list 表"""
    HUPU_POST_LIST_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "huputitle": "TEXT",
        "hupu_zone": "TEXT",
        "posturl": "TEXT",
        "replies": "TEXT",
        "tuijian_count": "TEXT",
        "fatietime": "TEXT",
        "addtime": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "liangping_count": "TEXT",
        "task_id": "TEXT"  # 添加主任务标识
    }
    
    HUPU_POST_LIST_UNIQUE = [
        'UNIQUE ("posturl" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="hupu_post_list",
        target_fields=HUPU_POST_LIST_TARGET_FIELDS,
        unique_constraints=HUPU_POST_LIST_UNIQUE,
        confirm_drop=False
    )


def create_hupu_score_list_table(db):
    """创建 hupu_score_list 表"""
    HUPU_SCORE_LIST_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "name": "TEXT",
        "time": "TEXT",
        "location": "TEXT",
        "comment": "TEXT",
        "reply_comment": "TEXT",
        "like_count": "TEXT",
        "score": "TEXT",
        "score_title": "TEXT",
        "addtime": "DATETIME",
        "scoreurl": "TEXT",
        "task_id": "TEXT"  # 添加主任务标识
    }
    
    HUPU_SCORE_LIST_UNIQUE = [
        'UNIQUE ("scoreurl", "name", "time" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="hupu_score_list",
        target_fields=HUPU_SCORE_LIST_TARGET_FIELDS,
        unique_constraints=HUPU_SCORE_LIST_UNIQUE,
        confirm_drop=False
    )


def create_hupu_detail_list_table(db):
    """创建 hupu_detail_list 表"""
    HUPU_DETAIL_LIST_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "fabucontent": "TEXT NOT NULL",
        "nickname": "TEXT",
        "replycontent": "TEXT",
        "floor": "TEXT",
        "ipaddress": "TEXT",
        "posttitle": "TEXT",
        "like_count": "TEXT",
        "posturl": "TEXT",
        "replytime": "TEXT",
        "addtime": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "reply_count": "TEXT",
        "task_id": "TEXT"
    }
    
    HUPU_DETAIL_LIST_UNIQUE = [
        'UNIQUE ("posturl", "floor" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="hupu_detail_list",
        target_fields=HUPU_DETAIL_LIST_TARGET_FIELDS,
        unique_constraints=HUPU_DETAIL_LIST_UNIQUE,
        confirm_drop=False
    )


def update_hupu_detail_list_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 hupu_detail_list 表结构"""
    HUPU_DETAIL_LIST_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "fabucontent": "TEXT NOT NULL",
        "nickname": "TEXT",
        "replycontent": "TEXT",
        "floor": "TEXT",
        "ipaddress": "TEXT",
        "posttitle": "TEXT",
        "like_count": "TEXT",
        "posturl": "TEXT",
        "replytime": "TEXT",
        "addtime": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "reply_count": "TEXT",
        "task_id": "TEXT"
    }
    
    HUPU_DETAIL_LIST_UNIQUE = [
        'UNIQUE ("posturl", "floor" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="hupu_detail_list",
        target_fields=HUPU_DETAIL_LIST_TARGET_FIELDS,
        unique_constraints=HUPU_DETAIL_LIST_UNIQUE,
        confirm_drop=confirm_drop
    )


def update_ai_analysis_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 ai_analysis 表结构"""
    AI_ANALYSIS_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "task_name": "TEXT",
        "status": "TEXT",
        "msg": "TEXT",
        "remarks": "TEXT",
        "task_id": "TEXT",
        "type": "TEXT",
        "ai_sumup": "TEXT"
    }
    
    return update_table_structure(
        db=db,
        table_name="ai_analysis",
        target_fields=AI_ANALYSIS_TARGET_FIELDS,
        confirm_drop=confirm_drop
    )


def update_hupu_post_list_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 hupu_post_list 表结构"""
    HUPU_POST_LIST_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "huputitle": "TEXT",
        "hupu_zone": "TEXT",
        "posturl": "TEXT",
        "replies": "TEXT",
        "tuijian_count": "TEXT",
        "fatietime": "TEXT",
        "addtime": "DATETIME DEFAULT CURRENT_TIMESTAMP",
        "liangping_count": "TEXT",
        "task_id": "TEXT"
    }
    
    HUPU_POST_LIST_UNIQUE = [
        'UNIQUE ("posturl" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="hupu_post_list",
        target_fields=HUPU_POST_LIST_TARGET_FIELDS,
        unique_constraints=HUPU_POST_LIST_UNIQUE,
        confirm_drop=confirm_drop
    )


def update_hupu_score_list_table_structure(db, confirm_drop: bool = True) -> bool:
    """更新 hupu_score_list 表结构"""
    HUPU_SCORE_LIST_TARGET_FIELDS = {
        "id": "INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT",
        "name": "TEXT",
        "time": "TEXT",
        "location": "TEXT",
        "comment": "TEXT",
        "reply_comment": "TEXT",
        "like_count": "TEXT",
        "score": "TEXT",
        "score_title": "TEXT",
        "addtime": "DATETIME",
        "scoreurl": "TEXT",
        "task_id": "TEXT"
    }
    
    HUPU_SCORE_LIST_UNIQUE = [
        'UNIQUE ("scoreurl", "name", "time" ASC)'
    ]
    
    return update_table_structure(
        db=db,
        table_name="hupu_score_list",
        target_fields=HUPU_SCORE_LIST_TARGET_FIELDS,
        unique_constraints=HUPU_SCORE_LIST_UNIQUE,
        confirm_drop=confirm_drop
    )


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 初始化 hupu 数据库
    print("=== 初始化 hupu 数据库 ===")
    success = initialize_hupu_database()
    if success:
        print("✅ hupu 数据库初始化成功")
    else:
        print("❌ hupu 数据库初始化失败")