# 配置文件_系统配置/common_config.py
import os
import time
from datetime import datetime

from loguru import logger

from gui.utils.jiami import LoginDataEncryptor
from lite_modules.snow_flake import SnowflakeGenerator
# 导入基础依赖（仅导入不产生循环的模块）
from modules.classSQLite import SQLiteDB
from modules.config_manager import ConfigManager


# ===== 数据库连接管理器 =====
class DatabaseConnectionManager:
    """数据库连接管理器，维护不同表的数据库连接"""
    
    def __init__(self):
        self.connections = {}
    
    def get_connection(self, table_name):
        """根据表名获取对应的数据库连接"""
        if table_name in self.connections:
            return self.connections[table_name]
        
        # 根据表名确定使用哪个数据库
        if table_name in ["task", "shop", "ai_analysis"]:
            # 使用主数据库
            if db is not None:
                self.connections[table_name] = db
                return db
        elif table_name in ["hupu_post_list", "hupu_detail_list", "hupu_score_list"]:
            # 使用虎扑数据库
            if hupu_db is not None:
                self.connections[table_name] = hupu_db
                return hupu_db
        
        # 如果没有找到对应的数据库，返回主数据库作为默认
        if db is not None:
            self.connections[table_name] = db
            return db
        
        return None
    
    def close_all(self):
        """关闭所有连接"""
        self.connections.clear()

# 创建全局数据库连接管理器实例
db_manager = DatabaseConnectionManager()

# ===== 工具函数 =====
def get_current_time():
    """返回当前时间 格式 2025-08-19 14:25:13"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def global_db_close():
    """
    安全关闭所有数据库并合并 WAL 文件
    关闭 ikun.db 和 hupu.db 两个数据库
    """
    try:
        import sqlite3
        from loguru import logger

        # 定义需要关闭的数据库列表
        databases_to_close = []
        
        # 添加主数据库
        if db is not None:
            databases_to_close.append(('ikun', db))
        
        # 添加 hupu 数据库
        if hupu_db is not None:
            databases_to_close.append(('hupu', hupu_db))
        
        # 逐个关闭数据库
        for db_name, db_instance in databases_to_close:
            try:
                # 第一步：执行 WAL 检查点，合并 -wal 和 -shm 文件
                try:
                    # 获取数据库路径
                    db_path = db_instance.db_path
                    if db_path and db_path != ":memory:":
                        # 用一个新的连接来执行检查点（确保所有写操作完成）
                        checkpoint_conn = sqlite3.connect(db_path)
                        checkpoint_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        checkpoint_conn.commit()
                        checkpoint_conn.close()
                        logger.info(f"✅ {db_name} 数据库 WAL 检查点完成，数据库文件已合并")
                except Exception as e:
                    logger.warning(f"⚠️ {db_name} 数据库 WAL 检查点失败（继续关闭）| 错误: {str(e)[:50]}")

                # 第二步：关闭主连接
                if hasattr(db_instance, '_thread_local') and hasattr(db_instance._thread_local, 'connection'):
                    try:
                        db_instance._thread_local.connection.close()
                        delattr(db_instance._thread_local, 'connection')
                    except:
                        pass

                # 第三步：关闭异步连接
                if hasattr(db_instance, '_async_conn') and db_instance._async_conn:
                    try:
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(db_instance._async_conn.close())
                            else:
                                asyncio.run(db_instance._async_conn.close())
                        except RuntimeError:
                            pass
                    except:
                        pass
                    db_instance._async_conn = None

                # 第四步：关闭线程池
                if hasattr(db_instance, '_executor'):
                    try:
                        db_instance._executor.shutdown(wait=False)
                    except:
                        pass
                
                logger.info(f"✅ {db_name} 数据库已安全关闭")
            except Exception as e:
                logger.warning(f"⚠️ {db_name} 数据库关闭异常（非致命）| 错误: {str(e)[:50]}")

        logger.info("✅ 所有数据库已安全关闭，防止文件损坏")
    except Exception as e:
        from loguru import logger
        logger.warning(f"⚠️ 数据库关闭异常（非致命）| 错误: {str(e)[:50]}")


# 初始化变量，防止导入失败
db = None
hupu_db = None
config_manager = None
max_concurrent_tasks = 800
modify_price_concurrent = 2
upload_real_pic_concurrent = 2
jit_govern_concurrent = 2
hupu_post_list_concurrent = 2
hupu_detail_list_concurrent = 2
hupu_score_list_concurrent = 2
task_concurrent_config = {
    "核价": 2,
    "上传实拍图": 2,
    "JIT库存": 2,
    "default": 800
}
upload_pic_check_rules_path = "配置文件_实拍图配置/upload_pic_check.json"
modify_price_excels_path = "配置文件_工具配置表/"

def create_db_config(config_path: str, db_path: str):
    """
    创建数据库配置文件
    
    Args:
        config_path: 配置文件路径
        db_path: 数据库文件路径
    """
    import json
    
    config = {
        "db_path": db_path,
        "timeout": 30.0,
        "check_same_thread": False,
        "enable_foreign_keys": True,
        "journal_mode": "WAL",
        "cache_size": -20000,
        "synchronous": "NORMAL",
        "pool_config": {
            "max_connections": 9999,
            "min_connections": 1,
            "connection_timeout": 30.0,
            "idle_timeout": 300.0,
            "pool_recycle": 3600,
            "pool_pre_ping": True
        },
        "debug": False
    }
    
    # 确保配置目录存在
    config_dir = os.path.dirname(config_path)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    
    # 写入配置文件
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2, separators=(",", ": "))
    
    logger.info(f"✅ 数据库配置文件已创建: {config_path}")

def initialize_ikun_database():
    """
    初始化 ikun 数据库
    """
    global db, config_manager
    
    try:
        ikun_config_path = "./配置文件_系统配置/db_config.json"
        ikun_db_path = "./配置文件_系统配置/ikun.db"
        
        # 如果配置文件不存在，创建它
        if not os.path.exists(ikun_config_path):
            create_db_config(ikun_config_path, ikun_db_path)
        else:
            logger.info(f"✅ 数据库配置文件已存在: {ikun_config_path}")
        db = SQLiteDB(ikun_config_path, debug=True)
        config_manager = ConfigManager(db)
        logger.info("✅ ikun 数据库初始化成功")
        return True
    except Exception as e:
        logger.warning(f"初始化 ikun 数据库失败: {e}")
        db = None
        config_manager = None
        return False

def initialize_hupu_database():
    """
    初始化 hupu 数据库
    """
    global hupu_db
    
    try:
        hupu_config_path = "./配置文件_系统配置/hupu_db_config.json"
        hupu_db_path = "./配置文件_系统配置/hupu.db"
        
        # 如果配置文件不存在，创建它
        if not os.path.exists(hupu_config_path):
            create_db_config(hupu_config_path, hupu_db_path)
        else:
            logger.info(f"✅ 数据库配置文件已存在: {hupu_config_path}")
        hupu_db = SQLiteDB(hupu_config_path, debug=True)
        logger.info("✅ hupu 数据库初始化成功")
        return True
    except Exception as e:
        logger.warning(f"初始化 hupu 数据库失败: {e}")
        hupu_db = None
        return False

def initialize_all_databases(permissions=None):
    """
    统一初始化所有数据库和表结构
    
    Args:
        permissions: 权限列表，用于决定初始化哪些数据库
                    包含 "temu", "caiwu", "spider", "ddos" 等
    
    Returns:
        bool: 是否全部初始化成功
    """
    if permissions is None:
        permissions = []
    
    success = True
    
    # 初始化 ikun 数据库（temu/caiwu 权限）
    if any(p in permissions for p in ["temu", "caiwu"]):
        try:
            initialize_ikun_database()
            logger.info("✅ ikun 数据库已初始化")
        except Exception as e:
            logger.error(f"ikun 数据库初始化失败: {e}")
            success = False
    
    # 初始化 hupu 数据库（spider 权限）
    if "spider" in permissions:
        try:
            initialize_hupu_database()
            logger.info("✅ hupu 数据库已初始化")
        except Exception as e:
            logger.error(f"hupu 数据库初始化失败: {e}")
            success = False
    
    # 初始化数据库表结构
    try:
        from utils.db_updater_ikun import initialize_database
        initialize_database()
        logger.info("✅ ikun 数据库表结构已初始化")
    except Exception as e:
        logger.error(f"数据库表结构初始化失败: {e}")
        success = False
    
    # 初始化 hupu 数据库表结构
    try:
        from utils.db_updater_spider import initialize_hupu_database as init_hupu_table
        init_hupu_table()
        logger.info("✅ hupu 数据库表结构已初始化")
    except Exception as e:
        logger.error(f"hupu数据库表结构初始化失败: {e}")
        success = False
    
    # 初始化 scheduled_tasks 数据库表结构
    try:
        from utils.scheduled_tasks_db_updater import initialize_scheduled_tasks_database
        initialize_scheduled_tasks_database()
        logger.info("✅ scheduled_tasks 数据库表结构已初始化")
    except Exception as e:
        logger.error(f"scheduled_tasks数据库表结构初始化失败: {e}")
        success = False
    
    # 修复定时任务表（移除外键约束）
    try:
        from utils.scheduled_tasks_db_updater import update_scheduled_tasks_table_structure
        if db is not None:
            repair_success = update_scheduled_tasks_table_structure(db, confirm_drop=False)
            if repair_success:
                logger.info("✅ 定时任务表修复成功")
            else:
                logger.warning("⚠️ 定时任务表修复失败")
    except Exception as e:
        logger.error(f"定时任务表修复异常: {e}")
    
    # 写入初始化锁文件
    try:
        lock_file_path = "./config/lock.txt"
        lock_content = "初始化锁，若需重新初始化则删除数据库文件和本文件，最后重新启动程序即可"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
        
        # 写入文件
        with open(lock_file_path, "w", encoding="utf-8") as f:
            f.write(lock_content)
        
        logger.info("✅ 初始化锁文件已创建")
    except Exception as lock_error:
        logger.warning(f"创建初始化锁文件失败: {lock_error}")
    
    return success

try:
    # 默认初始化 ikun 数据库（兼容旧版本）
    initialize_ikun_database()
    
    # 默认初始化 hupu 数据库（兼容旧版本）
    initialize_hupu_database()

    # 全局配置变量（供其他模块导入）
    if config_manager is not None:
        # 初始值从配置表读取
        max_concurrent_tasks = int(config_manager.get_or_set_config("max_concurrent_tasks", "800", True))
        modify_price_concurrent = int(config_manager.get_or_set_config("modify_price_concurrent", "2"))
        expected_goods_place_concurrent = int(config_manager.get_or_set_config("expected_goods_place_concurrent", "2"))
        upload_real_pic_concurrent = int(config_manager.get_or_set_config("upload_real_pic_concurrent", "2"))
        jit_govern_concurrent = int(config_manager.get_or_set_config("jit_govern_concurrent", "2"))
        hupu_post_list_concurrent = int(config_manager.get_or_set_config("hupu_post_list_concurrent", "2"))
        hupu_detail_list_concurrent = int(config_manager.get_or_set_config("hupu_detail_list_concurrent", "2"))
        hupu_score_list_concurrent = int(config_manager.get_or_set_config("hupu_score_list_concurrent", "2"))
        apply_activity_concurrent = int(config_manager.get_or_set_config("apply_activity_concurrent", "2"))

        # 任务并发配置字典
        task_concurrent_config = {
            "核价": modify_price_concurrent,
            "期望到货地点": expected_goods_place_concurrent,
            "上传实拍图": upload_real_pic_concurrent,
            "JIT库存": jit_govern_concurrent,
            "虎扑帖子列表采集": hupu_post_list_concurrent,
            "虎扑帖子详情采集": hupu_detail_list_concurrent,
            "虎扑评分采集": hupu_score_list_concurrent,
            "报活动": apply_activity_concurrent,
            "default": max_concurrent_tasks
        }

        upload_pic_check_rules_path = config_manager.get_or_set_config("upload_pic_check_rules_path",
                                                                        "配置文件_实拍图配置/upload_pic_check.json",
                                                                        True)

        modify_price_excels_path = config_manager.get_or_set_config("modify_price_excels_path",
                                                                        "配置文件_工具配置表/",
                                                                        True)


except Exception as e:
    # 在记录错误日志之前先尝试安全关闭数据库
    try:
        if db is not None:
            db.close_safely()
        if hupu_db is not None:
            hupu_db.close_safely()
    except:
        pass
    logger.exception(f"❌ 初始化数据库失败: {e}")



# ===== 3. 初始化雪花生成器（无依赖）=====
generator = SnowflakeGenerator(worker_id=1, datacenter_id=1)
# uid = generator.generate_id()
encryptor = LoginDataEncryptor()