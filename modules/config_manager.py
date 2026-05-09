import json
import ast
from loguru import logger


class ConfigManager:
    """
    配置管理器（基础版热更新 + 类型自动转换）
    核心特性：
    1. 每次操作直接查询/更新数据库，修改配置后下一次调用立即生效
    2. 支持自动将字符串配置转换为 int/float/list/dict/tuple/bool 等类型
    """

    def __init__(self, db):
        """
        初始化配置管理器
        :param db: 数据库执行器（需支持 execute_sql 方法，和你现有代码的 db 一致）
        """
        self.db = db

    def _convert_value(self, value: str, value_type: str = "str") -> any:
        """
        内部工具函数：将字符串值转换为指定类型
        :param value: 原始字符串值
        :param value_type: 目标类型，支持：str/int/float/list/dict/tuple/bool
        :return: 转换后的值（转换失败返回原始值或对应类型的默认值）
        """
        if value is None or value == "":
            # 空值返回对应类型的默认值
            type_defaults = {
                "int": 0,
                "float": 0.0,
                "list": [],
                "dict": {},
                "tuple": (),
                "bool": False,
                "str": ""
            }
            return type_defaults.get(value_type, "")

        try:
            if value_type == "str":
                return str(value)
            elif value_type == "int":
                return int(value)
            elif value_type == "float":
                return float(value)
            elif value_type == "bool":
                # 兼容 "True"/"False" 或 "1"/"0" 格式
                lower_val = value.strip().lower()
                if lower_val in ("true", "1"):
                    return True
                elif lower_val in ("false", "0"):
                    return False
                return False
            elif value_type == "list":
                # 支持 JSON 格式或 Python 原生列表格式
                try:
                    return json.loads(value.replace("'", "\""))
                except:
                    return ast.literal_eval(value)
            elif value_type == "dict":
                # 支持 JSON 格式或 Python 原生字典格式
                try:
                    return json.loads(value.replace("'", "\""))
                except:
                    return ast.literal_eval(value)
            elif value_type == "tuple":
                # 先转列表再转元组
                try:
                    lst = json.loads(value.replace("'", "\""))
                except:
                    lst = ast.literal_eval(value)
                return tuple(lst)
            else:
                # 未知类型返回原始字符串
                return value
        except (json.JSONDecodeError, ast.literal_eval, SyntaxError, ValueError, TypeError):
            # 转换失败返回对应类型的默认值
            logger.warning(f"⚠️ 配置值类型转换失败：value={value}, target_type={value_type}，返回默认值")
            type_defaults = {
                "int": 0,
                "float": 0.0,
                "list": [],
                "dict": {},
                "tuple": (),
                "bool": False,
                "str": value
            }
            return type_defaults.get(value_type, value)

    def upsert_config(self, key: str, value: any, only_insert: bool = False) -> dict:
        """
        智能插入/更新配置（核心热更新函数）
        :param key: 配置键（字符串，唯一）
        :param value: 配置值（任意类型，自动转为字符串存储）
        :param only_insert: 是否仅新增（True=仅插入不存在的key，False=存在更新/不存在插入）
        :return: 操作结果字典
        """
        if not isinstance(key, str) or not key.strip():
            return {"code": -1, "msg": "配置键不能为空字符串", "data": {"oper_type": ""}}

        # 统一将值转为字符串存储（兼容所有类型）
        if isinstance(value, (list, dict, tuple)):
            value_str = json.dumps(value, ensure_ascii=False)
        else:
            value_str = str(value)

        try:
            # 1. 先查询是否存在该配置
            exist_sql = "SELECT id FROM config WHERE `key` = ? AND is_deleted = 0;"
            exist_result = self.db.execute_sql(exist_sql, params=(key.strip(),), fetch="fetch_one")

            if exist_result:
                # 仅新增模式，直接跳过
                if only_insert:
                    logger.info(f"✅ 配置已存在，跳过新增：key={key}")
                    return {
                        "code": 1,
                        "msg": "配置已存在，跳过新增",
                        "data": {"oper_type": "skip", "key": key}
                    }
                # 2. 存在则更新
                update_sql = """
                             UPDATE config
                             SET value       = ?, \
                                 update_time = datetime('now', '+8 hours')
                             WHERE `key` = ? \
                               AND is_deleted = 0; \
                             """
                self.db.execute_sql(update_sql, params=(value_str, key.strip()), fetch="none")
                return {
                    "code": 1,
                    "msg": "配置更新成功",
                    "data": {"oper_type": "update", "key": key, "value": value}
                }
            else:
                # 3. 不存在则插入
                insert_sql = """
                             INSERT INTO config (`key`, value, create_time, update_time, is_deleted)
                             VALUES (?, ?, datetime('now', '+8 hours'), datetime('now', '+8 hours'), 0); \
                             """
                self.db.execute_sql(insert_sql, params=(key.strip(), value_str), fetch="none")
                logger.info(f"✅ 配置新增成功：key={key}, value={value}")
                return {
                    "code": 1,
                    "msg": "配置新增成功",
                    "data": {"oper_type": "insert", "key": key, "value": value}
                }
        except Exception as e:
            logger.error(f"❌ 配置upsert失败：key={key}, error={e}")
            return {"code": -1, "msg": f"配置操作失败：{str(e)}", "data": {"oper_type": ""}}

    def get_or_set_config(self, key: str, default_value: any = "", force: bool = False, value_type: str = "str") -> any:
        """
        查询配置（不存在则自动创建并赋值默认值，热更新生效）
        :param key: 配置键（字符串）
        :param default_value: 默认值（任意类型）
        :param force: 是否强制覆盖现有值（默认 False）
        :param value_type: 返回值类型，支持：str/int/float/list/dict/tuple/bool
        :return: 转换后的配置值
        """
        if not isinstance(key, str) or not key.strip():
            logger.error("❌ 配置键不能为空字符串")
            return self._convert_value(str(default_value), value_type)

        try:
            if force:
                # 强制模式：直接覆盖并返回转换后的默认值
                self.upsert_config(key.strip(), default_value)
                return self._convert_value(str(default_value), value_type)

            # 非强制模式：先查是否存在
            query_sql = "SELECT value FROM config WHERE `key` = ? AND is_deleted = 0;"
            query_result = self.db.execute_sql(query_sql, params=(key.strip(),), fetch="fetch_one")

            if query_result and query_result.get("value") is not None:
                # 读取到值，转换为指定类型
                value = query_result["value"]
                return self._convert_value(value, value_type)
            else:
                # 不存在则创建，返回转换后的默认值
                logger.info(f"配置不存在，自动创建：key={key}, 默认值={default_value}")
                self.upsert_config(key.strip(), default_value)
                return self._convert_value(str(default_value), value_type)

        except Exception as e:
            logger.error(f"❌ 查询或设置配置失败：key={key}, error={e}")
            return self._convert_value(str(default_value), value_type)

    def batch_init_config(self, init_config: dict, value_type: str = "str") -> dict:
        """
        批量初始化配置（适合项目启动时加载基础配置）
        :param init_config: 初始化配置字典，格式：{"key1": "value1", "key2": "value2"}
        :param value_type: 批量转换的目标类型（默认str）
        :return: 批量操作结果
        """
        if not isinstance(init_config, dict):
            return {"code": -1, "msg": "初始化配置必须是字典类型", "data": {"success_count": 0, "fail_list": []}}

        success_count = 0
        skip_count = 0
        fail_list = []
        for key, value in init_config.items():
            # 转换为指定类型后再存储
            converted_value = self._convert_value(str(value), value_type)
            result = self.upsert_config(key, converted_value, only_insert=True)
            if result["code"] == 1:
                success_count += 1
                if result["data"]["oper_type"] == "skip":
                    skip_count += 1
            else:
                fail_list.append({"key": key, "reason": result["msg"]})

        if fail_list:
            logger.warning(
                f"⚠️ 批量初始化配置完成：成功{success_count}个（新增{success_count - skip_count}个，跳过{skip_count}个），失败{len(fail_list)}个")
            return {
                "code": -1,
                "msg": f"批量初始化完成，部分失败：成功{success_count}个（新增{success_count - skip_count}个，跳过{skip_count}个），失败{len(fail_list)}个",
                "data": {"success_count": success_count, "skip_count": skip_count, "fail_list": fail_list}
            }
        else:
            logger.info(
                f"✅ 批量初始化配置完成：全部成功，共{success_count}个（新增{success_count - skip_count}个，跳过{skip_count}个）")
            return {
                "code": 1,
                "msg": f"批量初始化配置成功，共{success_count}个（新增{success_count - skip_count}个，跳过{skip_count}个）",
                "data": {"success_count": success_count, "skip_count": skip_count, "fail_list": []}
            }

    def delete_config(self, key: str, soft_delete: bool = True) -> dict:
        """
        删除配置（默认软删除，更安全）
        :param key: 配置键
        :param soft_delete: 是否软删除（True-标记删除，False-物理删除）
        :return: 操作结果字典
        """
        if not isinstance(key, str) or not key.strip():
            return {"code": -1, "msg": "配置键不能为空字符串", "data": {}}

        try:
            if soft_delete:
                # 软删除：标记is_deleted=1
                delete_sql = "UPDATE config SET is_deleted = 1, update_time = datetime('now', '+8 hours') WHERE `key` = ?;"
                self.db.execute_sql(delete_sql, params=(key.strip(),), fetch="none")
                logger.info(f"✅ 配置软删除成功：key={key}")
                return {"code": 1, "msg": "配置软删除成功", "data": {"key": key, "delete_type": "soft"}}
            else:
                # 物理删除：谨慎使用
                delete_sql = "DELETE FROM config WHERE `key` = ?;"
                self.db.execute_sql(delete_sql, params=(key.strip(),), fetch="none")
                logger.warning(f"⚠️ 配置物理删除成功：key={key}（不可恢复）")
                return {"code": 1, "msg": "配置物理删除成功（不可恢复）", "data": {"key": key, "delete_type": "hard"}}
        except Exception as e:
            logger.error(f"❌ 删除配置失败：key={key}, error={e}")
            return {"code": -1, "msg": f"删除配置失败：{str(e)}", "data": {}}

    def get_all_config(self, only_active: bool = True, value_type: str = "str") -> dict:
        """
        全量查询配置（用于核对/备份）
        :param only_active: 是否只查未删除的配置（True-仅未删除，False-包含已删除）
        :param value_type: 返回值的目标类型（默认str）
        :return: 转换后的配置字典
        """
        try:
            if only_active:
                query_sql = "SELECT `key`, value FROM config WHERE is_deleted = 0;"
            else:
                query_sql = "SELECT `key`, value FROM config;"

            query_result = self.db.execute_sql(query_sql, fetch="fetch")
            # 转换所有值为指定类型
            config_dict = {
                item["key"]: self._convert_value(item["value"], value_type)
                for item in query_result
            }
            return config_dict
        except Exception as e:
            logger.error(f"❌ 全量查询配置失败：{e}")
            return {}


# ====================== 初始化配置字典（贴合你的核价业务） ======================
INIT_TEMU_CONFIG = {
    # 核价业务基础参数
    "max_concurrent_tasks": "200",  # 核价每页SKU数
    "timeout_seconds": "3600",  # 超时时间（int）
    "price_ranges": "[10, 50, 100]",  # 价格区间（list）
    "shop_config": '{"shop1": "active", "shop2": "inactive"}',  # 店铺配置（dict）
    "enable_auto_price": "True",  # 是否自动核价（bool）
    "priority_tuple": "(1,2,3)"  # 优先级（tuple）
}

# ====================== 使用示例（演示类型转换功能） ======================
if __name__ == "__main__":
    # 1. 初始化配置管理器（传入你的数据库执行器db）
    # from config.middleware_config import db
    # config_manager = ConfigManager(db)

    # 注：以下为模拟测试（替换为你的真实db即可运行）
    class MockDB:
        """模拟数据库执行器（仅用于测试）"""

        def execute_sql(self, sql, params=(), fetch="none"):
            if fetch == "fetch_one":
                return None  # 模拟配置不存在
            elif fetch == "fetch":
                return []
            return {"code": 1}


    mock_db = MockDB()
    config_manager = ConfigManager(mock_db)

    # 2. 批量初始化基础配置
    init_result = config_manager.batch_init_config(INIT_TEMU_CONFIG)
    print("批量初始化结果：", init_result)

    # 3. 示例1：读取int类型配置
    max_tasks = config_manager.get_or_set_config("max_concurrent_tasks", "200", value_type="int")
    print(f"max_concurrent_tasks（int）: {max_tasks}, 类型: {type(max_tasks)}")  # 200 <class 'int'>

    # 4. 示例2：读取list类型配置
    price_ranges = config_manager.get_or_set_config("price_ranges", "[10,50,100]", value_type="list")
    print(f"price_ranges（list）: {price_ranges}, 类型: {type(price_ranges)}")  # [10,50,100] <class 'list'>

    # 5. 示例3：读取dict类型配置
    shop_config = config_manager.get_or_set_config("shop_config", '{"shop1":"active"}', value_type="dict")
    print(f"shop_config（dict）: {shop_config}, 类型: {type(shop_config)}")  # {'shop1':'active'} <class 'dict'>

    # 6. 示例4：读取bool类型配置
    enable_auto = config_manager.get_or_set_config("enable_auto_price", "True", value_type="bool")
    print(f"enable_auto_price（bool）: {enable_auto}, 类型: {type(enable_auto)}")  # True <class 'bool'>

    # 7. 示例5：读取tuple类型配置
    priority = config_manager.get_or_set_config("priority_tuple", "(1,2,3)", value_type="tuple")
    print(f"priority_tuple（tuple）: {priority}, 类型: {type(priority)}")  # (1,2,3) <class 'tuple'>

    # 8. 示例6：更新并读取float类型配置
    config_manager.upsert_config("tax_rate", "0.08")
    tax_rate = config_manager.get_or_set_config("tax_rate", "0.08", value_type="float")
    print(f"tax_rate（float）: {tax_rate}, 类型: {type(tax_rate)}")  # 0.08 <class 'float'>
