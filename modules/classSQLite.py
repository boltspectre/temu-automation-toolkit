"""
SQLite 现代化操作类
支持：异步操作、连接池、事务、JSON、Type Hints、ORM风格
"""
from __future__ import annotations
import logging
import asyncio
import contextlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import (
    Any, Dict, List, Optional, Tuple, Union, TypeVar
)

import aiosqlite
import chardet

# 类型变量
T = TypeVar('T')
ModelType = TypeVar('ModelType', bound='BaseModel')
ResultT = TypeVar('ResultT')


# 连接池配置
@dataclass
class PoolConfig:
    """连接池配置"""
    max_connections: int = 9999
    min_connections: int = 1
    connection_timeout: float = 30.0
    idle_timeout: float = 300.0
    pool_recycle: int = 3600
    pool_pre_ping: bool = True


@dataclass
class QueryCondition:
    """查询条件"""
    field: str
    operator: str = "="
    value: Any = None
    logic: str = "AND"  # AND, OR
    is_raw: bool = False  # 是否原生SQL


@dataclass
class OrderBy:
    """排序条件"""
    field: str
    ascending: bool = True


@dataclass
class JoinClause:
    """连接条件"""
    table: str
    on: str
    type: str = "INNER"  # INNER, LEFT, RIGHT, FULL


def load_db_config(config_path: str = "./db_config.json") -> dict:
    """加载数据库配置文件（修复编码问题）"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"数据库配置文件不存在: {config_path}")

    # 第一步：检测文件编码（解决乱码核心）
    with open(config_file, "rb") as f:
        raw_data = f.read()
        detect_result = chardet.detect(raw_data)
        file_encoding = detect_result["encoding"] or "utf-8"

    # 第二步：用检测到的编码读取文件（兼容GBK/UTF-8等）
    try:
        with open(config_file, "r", encoding=file_encoding) as f:
            config = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # 兜底：先尝试UTF-8，再尝试GBK
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            with open(config_file, "r", encoding="gbk", errors="ignore") as f:
                config = json.load(f)

    # 设置默认值，防止配置项缺失
    default_config = {
        "db_path": ":memory:",
        "timeout": 30.0,
        "check_same_thread": False,
        "enable_foreign_keys": True,
        "journal_mode": "WAL",
        "cache_size": -2000,
        "synchronous": "NORMAL"
    }
    # 合并配置（用户配置覆盖默认值）
    default_config.update(config)
    return default_config


class QueryBuilder:
    """查询构建器"""

    def __init__(self, table: str):
        self.table = table
        self._select = ["*"]
        self._where = []
        self._order_by = []
        self._group_by = []
        self._having = []
        self._joins = []
        self._limit = None
        self._offset = None
        self._distinct = False
        self._params = []

    def select(self, *fields: str) -> QueryBuilder:
        """选择字段"""
        if fields:
            self._select = list(fields)
        return self

    def where(self, field: str, value: Any = None, operator: str = "=") -> QueryBuilder:
        """WHERE条件"""
        if value is None and operator == "=":
            operator = "IS"
        elif value is None and operator == "!=":
            operator = "IS NOT"

        self._where.append(QueryCondition(field, operator, value))
        if value is not None:
            self._params.append(value)
        return self

    def where_raw(self, sql: str, *params) -> QueryBuilder:
        """原生WHERE条件"""
        self._where.append(QueryCondition("", "RAW", None, is_raw=True))
        self._params.extend(params)
        return self

    def or_where(self, field: str, value: Any = None, operator: str = "=") -> QueryBuilder:
        """OR WHERE条件"""
        if self._where:
            self._where.append(QueryCondition("", "OR", None, logic="OR", is_raw=True))
        return self.where(field, value, operator)

    def order_by(self, field: str, ascending: bool = True) -> QueryBuilder:
        """排序"""
        self._order_by.append(OrderBy(field, ascending))
        return self

    def limit(self, count: int) -> QueryBuilder:
        """限制数量"""
        self._limit = count
        return self

    def offset(self, offset: int) -> QueryBuilder:
        """偏移量"""
        self._offset = offset
        return self

    def join(self, table: str, on: str, type: str = "INNER") -> QueryBuilder:
        """连接表"""
        self._joins.append(JoinClause(table, on, type))
        return self

    def group_by(self, *fields: str) -> QueryBuilder:
        """分组"""
        self._group_by.extend(fields)
        return self

    def having(self, sql: str, *params) -> QueryBuilder:
        """HAVING条件"""
        self._having.append((sql, params))
        self._params.extend(params)
        return self

    def distinct(self) -> QueryBuilder:
        """去重"""
        self._distinct = True
        return self

    def build(self) -> Tuple[str, list]:
        """构建SQL"""
        sql_parts = ["SELECT"]

        if self._distinct:
            sql_parts.append("DISTINCT")

        sql_parts.append(", ".join(self._select))
        sql_parts.append(f"FROM {self.table}")

        # 处理JOIN
        for join in self._joins:
            sql_parts.append(f"{join.type} JOIN {join.table} ON {join.on}")

        # 处理WHERE
        if self._where:
            where_clauses = []
            for condition in self._where:
                if condition.is_raw:
                    where_clauses.append(condition.value or "")
                else:
                    placeholder = "?" if condition.value is not None else "NULL"
                    where_clauses.append(f"{condition.field} {condition.operator} {placeholder}")

            sql_parts.append("WHERE " + " ".join(where_clauses))

        # 处理GROUP BY
        if self._group_by:
            sql_parts.append(f"GROUP BY {', '.join(self._group_by)}")

        # 处理HAVING
        if self._having:
            having_clauses = [h[0] for h in self._having]
            sql_parts.append("HAVING " + " AND ".join(having_clauses))

        # 处理ORDER BY
        if self._order_by:
            order_clauses = []
            for order in self._order_by:
                direction = "ASC" if order.ascending else "DESC"
                order_clauses.append(f"{order.field} {direction}")
            sql_parts.append(f"ORDER BY {', '.join(order_clauses)}")

        # 处理LIMIT和OFFSET
        if self._limit is not None:
            sql_parts.append(f"LIMIT {self._limit}")
            if self._offset is not None:
                sql_parts.append(f"OFFSET {self._offset}")

        sql = " ".join(sql_parts)
        return sql, self._params


class SQLiteTypeAdapter:
    """SQLite类型适配器"""

    @staticmethod
    def adapt_json(value: Any) -> str:
        """适配JSON类型"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def convert_json(value: bytes) -> Any:
        """转换JSON类型"""
        if value is None:
            return None
        try:
            return json.loads(value.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return value.decode('utf-8')

    @staticmethod
    def adapt_datetime(value: datetime) -> str:
        """适配datetime类型"""
        return value.isoformat()

    @staticmethod
    def convert_datetime(value: bytes) -> datetime:
        """转换datetime类型"""
        return datetime.fromisoformat(value.decode('utf-8'))

    @staticmethod
    def adapt_date(value: date) -> str:
        """适配date类型"""
        return value.isoformat()

    @staticmethod
    def convert_date(value: bytes) -> date:
        """转换date类型"""
        return date.fromisoformat(value.decode('utf-8'))

    @classmethod
    def register_adapters(cls):
        """注册类型适配器"""
        sqlite3.register_adapter(dict, cls.adapt_json)
        sqlite3.register_adapter(list, cls.adapt_json)
        sqlite3.register_adapter(datetime, cls.adapt_datetime)
        sqlite3.register_adapter(date, cls.adapt_date)

        sqlite3.register_converter("JSON", cls.convert_json)
        sqlite3.register_converter("DATETIME", cls.convert_datetime)
        sqlite3.register_converter("DATE", cls.convert_date)


class ConnectionPool:
    """SQLite连接池（简化版，线程安全）"""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def create_connection(self, db_path: str, **kwargs) -> sqlite3.Connection:
        """创建新的数据库连接（每个线程调用一次）"""
        # 从外部传入的kwargs中获取配置（由SQLiteDB实例传递）
        timeout = kwargs.get("timeout", 30.0)
        check_same_thread = kwargs.get("check_same_thread", False)
        enable_foreign_keys = kwargs.get("enable_foreign_keys", True)
        journal_mode = kwargs.get("journal_mode", "WAL")
        cache_size = kwargs.get("cache_size", -2000)
        synchronous = kwargs.get("synchronous", "NORMAL")

        conn = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=timeout,
            check_same_thread=check_same_thread  # 使用配置值
        )
        conn.row_factory = sqlite3.Row

        # 应用配置中的PRAGMA参数
        conn.execute(f"PRAGMA foreign_keys = {'ON' if enable_foreign_keys else 'OFF'}")
        conn.execute(f"PRAGMA journal_mode = {journal_mode}")
        conn.execute(f"PRAGMA cache_size = {cache_size}")
        conn.execute(f"PRAGMA synchronous = {synchronous}")

        return conn



class BaseModel:
    """基础模型类"""

    __tablename__: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__tablename__:
            cls.__tablename__ = cls.__name__.lower()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseModel:
        """从字典创建实例"""
        return cls(**data)

    def to_dict(self, exclude: List[str] = None) -> Dict[str, Any]:
        """转换为字典"""
        if exclude is None:
            exclude = []
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith('_') and k not in exclude}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.to_dict()}>"


class SQLiteDB:
    """
    现代化SQLite操作类
    特性：
    1. 同步/异步支持
    2. 连接池
    3. ORM风格操作
    4. 事务支持
    5. JSON支持
    6. 类型注解
    7. 查询构建器
    """

    def __init__(
            self,
            config_path: str = "./db_config.json",
            *,
            pool_config: Optional[PoolConfig] = None,
            logger: Optional[logging.Logger] = None,
            debug: bool = False
    ):
        """
        初始化SQLite数据库

        Args:
            db_path: 数据库文件路径，:memory: 表示内存数据库
            pool_config: 连接池配置
            logger: 日志记录器
            debug: 调试模式
        """
        # 加载配置文件
        self.config = load_db_config(config_path)
        # 从配置中读取核心参数
        self.db_path = self.config["db_path"]
        self.timeout = self.config["timeout"]
        self.check_same_thread = self.config["check_same_thread"]
        self.enable_foreign_keys = self.config["enable_foreign_keys"]
        self.journal_mode = self.config["journal_mode"]
        self.cache_size = self.config["cache_size"]
        self.synchronous = self.config["synchronous"]

        self.pool_config = pool_config or PoolConfig()
        self.logger = logger or logging.getLogger(__name__)
        self.debug = debug

        # 注册类型适配器
        SQLiteTypeAdapter.register_adapters()

        # 连接池
        self._pool = ConnectionPool()
        self._thread_local = threading.local()

        # 线程池用于异步操作
        self._executor = ThreadPoolExecutor(max_workers=self.pool_config.max_connections)

        # 异步连接
        self._async_conn = None

        self.logger.info(f"SQLiteDB initialized: {self.db_path} (config from {config_path})")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        if not hasattr(self._thread_local, 'connection'):
            # 传递配置参数到连接池
            self._thread_local.connection = self._pool.create_connection(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=self.check_same_thread,
                enable_foreign_keys=self.enable_foreign_keys,
                journal_mode=self.journal_mode,
                cache_size=self.cache_size,
                synchronous=self.synchronous
            )
        return self._thread_local.connection

    # ========== 基本CRUD操作 ==========

    def execute_sql(
            self,
            sql: str,
            params: Union[Tuple, List, Dict, None] = None,
            *,
            fetch: str = "none",  # none/fetch/fetch_one
            commit: bool = True
    ) -> Union[List[Dict], Dict, int, None]:
        """
        万能 SQL 执行方法（对外暴露的通用接口）
        :param sql: 任意 SQL 语句
        :param params: SQL 参数（元组/列表/字典）
        :param fetch: 结果获取方式：
            - "none": 不获取结果（默认，适用于 DML/DDL）
            - "fetch": 获取所有结果（适用于 SELECT）
            - "fetch_one": 获取单条结果（适用于 SELECT 单条）
        :param commit: 是否自动提交事务（DML 操作建议开启）
        :return: 执行结果：
            - SELECT(fetch): 字典列表
            - SELECT(fetch_one): 单条字典/None
            - INSERT: 自增 ID（整数）
            - UPDATE/DELETE: 受影响行数（整数）
            - DDL: None
        """
        if fetch not in ["none", "fetch", "fetch_one"]:
            raise ValueError("fetch 参数仅支持: none/fetch/fetch_one")

        # 调用私有 _execute 方法执行 SQL
        return self._execute(
            sql=sql,
            params=params,
            fetch=fetch == "fetch",
            fetch_one=fetch == "fetch_one",
            commit=commit
        )

    def _execute(
            self,
            sql: str,
            params: Union[Tuple, Dict, List] = None,
            *,
            fetch: bool = False,
            fetch_one: bool = False,
            commit: bool = True
    ) -> Union[List[Dict], Dict, int, None]:
        """
        内部执行 SQL 语句（修复提交逻辑）
        """
        conn = self._get_connection()
        cursor = None

        try:
            cursor = conn.cursor()

            if self.debug:
                self.logger.debug(f"SQL: {sql}, Params: {params}")

            if params:
                if isinstance(params, dict):
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # 处理查询结果
            if fetch:
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            elif fetch_one:
                row = cursor.fetchone()
                return dict(row) if row else None

            # 处理 DML/DDL 结果
            result = None
            sql_upper = sql.strip().upper()
            if sql_upper.startswith("INSERT"):
                result = cursor.lastrowid  # 插入返回自增 ID
            elif sql_upper.startswith(("UPDATE", "DELETE")):
                result = cursor.rowcount  # 更新/删除返回受影响行数

            # 修复：强制提交，移除 conn.in_transaction 判断
            if commit:
                conn.commit()

            return result

        except sqlite3.Error as e:
            if conn.in_transaction:
                conn.rollback()
            self.logger.error(f"SQL Error: {e}, SQL: {sql}")
            raise
        finally:
            if cursor:
                cursor.close()

    def insert(
            self,
            table: str,
            data: Dict[str, Any],
            *,
            on_conflict: str = None,
            return_id: bool = True
    ) -> Optional[int]:
        if not data:
            raise ValueError("Insert data cannot be empty")

        columns = []
        placeholders = []
        params = []

        # 分离普通值和原生SQL值
        for col, val in data.items():
            columns.append(col)
            # 标记原生SQL值（比如以 "SQL:" 开头）
            if isinstance(val, str) and val.startswith("SQL:"):
                placeholders.append(val[4:])  # 去掉前缀，直接拼到SQL
            else:
                placeholders.append("?")
                params.append(val)

        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

        if on_conflict:
            sql += f" ON CONFLICT {on_conflict}"

        result = self._execute(sql, tuple(params), commit=True)

        if return_id and result is not None:
            return result
        return None

    def insert_many(
            self,
            table: str,
            data_list: List[Dict[str, Any]],
            *,
            batch_size: int = 1000
    ) -> int:
        """
        批量插入数据

        Args:
            table: 表名
            data_list: 数据字典列表
            batch_size: 批量大小

        Returns:
            插入的总行数
        """
        if not data_list:
            return 0

        total_rows = 0
        columns = data_list[0].keys()
        columns_str = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))

        sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

        # 分批插入
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            values = [tuple(row[col] for col in columns) for row in batch]

            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.executemany(sql, values)
                total_rows += cursor.rowcount
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                self.logger.error(f"Batch insert error: {e}")
                raise
            finally:
                cursor.close()

        return total_rows

    def update(
            self,
            table: str,
            data: Dict[str, Any],
            where: Optional[Dict[str, Any]] = None,
            *,
            where_raw: Optional[str] = None,
            where_params: Optional[list] = None
    ) -> int:
        """
        更新数据

        Args:
            table: 表名
            data: 更新数据
            where: WHERE条件字典
            where_raw: 原生WHERE条件
            where_params: WHERE参数

        Returns:
            影响行数
        """
        if not data:
            raise ValueError("Update data cannot be empty")

        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        params = list(data.values())

        sql = f"UPDATE {table} SET {set_clause}"

        if where or where_raw:
            sql += " WHERE "
            if where:
                where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
                sql += where_clause
                params.extend(where.values())
            elif where_raw:
                sql += where_raw
                if where_params:
                    params.extend(where_params)

        result = self._execute(sql, params, commit=True)
        return result or 0

    def delete(
            self,
            table: str,
            where: Optional[Dict[str, Any]] = None,
            *,
            where_raw: Optional[str] = None,
            where_params: Optional[list] = None
    ) -> int:
        """
        删除数据

        Args:
            table: 表名
            where: WHERE条件字典
            where_raw: 原生WHERE条件
            where_params: WHERE参数

        Returns:
            影响行数
        """
        sql = f"DELETE FROM {table}"
        params = []

        if where or where_raw:
            sql += " WHERE "
            if where:
                where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
                sql += where_clause
                params = list(where.values())
            elif where_raw:
                sql += where_raw
                if where_params:
                    params = where_params

        result = self._execute(sql, params, commit=True)
        return result or 0

    def select(
            self,
            table: str,
            *,
            fields: Optional[List[str]] = None,
            where: Optional[Dict[str, Any]] = None,
            where_raw: Optional[str] = None,
            where_params: Optional[list] = None,
            order_by: Optional[str] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None,
            distinct: bool = False
    ) -> List[Dict]:
        """
        查询数据

        Args:
            table: 表名
            fields: 查询字段
            where: WHERE条件字典
            where_raw: 原生WHERE条件
            where_params: WHERE参数
            order_by: 排序
            limit: 限制数量
            offset: 偏移量
            distinct: 是否去重

        Returns:
            结果列表
        """
        select_fields = ", ".join(fields) if fields else "*"
        if distinct:
            select_fields = f"DISTINCT {select_fields}"

        sql = f"SELECT {select_fields} FROM {table}"
        params = []

        if where or where_raw:
            sql += " WHERE "
            if where:
                where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
                sql += where_clause
                params = list(where.values())
            elif where_raw:
                sql += where_raw
                if where_params:
                    params = where_params

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit is not None:
            sql += f" LIMIT {limit}"
            if offset is not None:
                sql += f" OFFSET {offset}"

        return self._execute(sql, params, fetch=True) or []

    def select_one(
            self,
            table: str,
            *,
            fields: Optional[List[str]] = None,
            where: Optional[Dict[str, Any]] = None,
            where_raw: Optional[str] = None,
            where_params: Optional[list] = None
    ) -> Optional[Dict]:
        """
        查询单条数据

        Args:
            table: 表名
            fields: 查询字段
            where: WHERE条件字典
            where_raw: 原生WHERE条件
            where_params: WHERE参数

        Returns:
            单条结果或None
        """
        result = self.select(
            table,
            fields=fields,
            where=where,
            where_raw=where_raw,
            where_params=where_params,
            limit=1
        )
        return result[0] if result else None

    def count(
            self,
            table: str,
            *,
            where: Optional[Dict[str, Any]] = None,
            where_raw: Optional[str] = None,
            where_params: Optional[list] = None,
            column: str = "*"
    ) -> int:
        """
        计数

        Args:
            table: 表名
            where: WHERE条件字典
            where_raw: 原生WHERE条件
            where_params: WHERE参数
            column: 计数列

        Returns:
            数量
        """
        sql = f"SELECT COUNT({column}) as count FROM {table}"
        params = []

        if where or where_raw:
            sql += " WHERE "
            if where:
                where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
                sql += where_clause
                params = list(where.values())
            elif where_raw:
                sql += where_raw
                if where_params:
                    params = where_params

        result = self._execute(sql, params, fetch_one=True)
        return result["count"] if result else 0

    def exists(
            self,
            table: str,
            where: Optional[Dict[str, Any]] = None,
            *,
            where_raw: Optional[str] = None,
            where_params: Optional[list] = None
    ) -> bool:
        """
        检查记录是否存在

        Args:
            table: 表名
            where: WHERE条件字典
            where_raw: 原生WHERE条件
            where_params: WHERE参数

        Returns:
            是否存在
        """
        return self.count(table, where=where, where_raw=where_raw,
                          where_params=where_params, limit=1) > 0

    # ========== 查询构建器 ==========

    def query(self, table: str) -> QueryBuilder:
        """
        获取查询构建器

        Args:
            table: 表名

        Returns:
            查询构建器
        """
        return QueryBuilder(table)

    def execute_query(self, builder: QueryBuilder) -> List[Dict]:
        """
        执行查询构建器

        Args:
            builder: 查询构建器

        Returns:
            结果列表
        """
        sql, params = builder.build()
        return self._execute(sql, params, fetch=True) or []

    # ========== 事务支持 ==========

    @contextlib.contextmanager
    def transaction(self):
        """
        事务上下文管理器
        使用示例：
            with db.transaction():
                db.insert(...)
                db.update(...)
        """
        conn = self._get_connection()
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def begin(self):
        """开始事务"""
        self._execute("BEGIN", commit=False)

    def commit(self):
        """提交事务"""
        conn = self._get_connection()
        conn.commit()

    def rollback(self):
        """回滚事务"""
        conn = self._get_connection()
        conn.rollback()

    # ========== 表操作 ==========

    def create_table(
            self,
            table: str,
            columns: Dict[str, str],
            *,
            primary_key: Optional[Union[str, List[str]]] = None,
            foreign_keys: Optional[List[Dict]] = None,
            indexes: Optional[List[Dict]] = None,
            if_not_exists: bool = True
    ) -> bool:
        """
        创建表

        Args:
            table: 表名
            columns: 列定义字典 {列名: 类型定义}
            primary_key: 主键
            foreign_keys: 外键
            indexes: 索引
            if_not_exists: 如果不存在则创建

        Returns:
            是否成功
        """
        column_defs = []
        for name, definition in columns.items():
            column_defs.append(f"{name} {definition}")

        sql = "CREATE TABLE"
        if if_not_exists:
            sql += " IF NOT EXISTS"

        sql += f" {table} (\n    " + ",\n    ".join(column_defs)

        if primary_key:
            if isinstance(primary_key, str):
                sql += f",\n    PRIMARY KEY ({primary_key})"
            else:
                sql += f",\n    PRIMARY KEY ({', '.join(primary_key)})"

        if foreign_keys:
            for fk in foreign_keys:
                sql += f",\n    FOREIGN KEY ({fk['column']}) "
                sql += f"REFERENCES {fk['ref_table']}({fk['ref_column']})"
                if 'on_delete' in fk:
                    sql += f" ON DELETE {fk['on_delete']}"
                if 'on_update' in fk:
                    sql += f" ON UPDATE {fk['on_update']}"

        sql += "\n)"

        try:
            self._execute(sql, commit=True)

            # 创建索引
            if indexes:
                for idx in indexes:
                    self.create_index(table, idx['columns'],
                                      unique=idx.get('unique', False),
                                      if_not_exists=idx.get('if_not_exists', True))

            return True
        except sqlite3.Error as e:
            self.logger.error(f"Create table error: {e}")
            return False

    def drop_table(self, table: str, if_exists: bool = True) -> bool:
        """
        删除表

        Args:
            table: 表名
            if_exists: 如果存在则删除

        Returns:
            是否成功
        """
        sql = "DROP TABLE"
        if if_exists:
            sql += " IF EXISTS"
        sql += f" {table}"

        try:
            self._execute(sql, commit=True)
            return True
        except sqlite3.Error as e:
            self.logger.error(f"Drop table error: {e}")
            return False

    def truncate_table(self, table: str) -> bool:
        """
        清空表

        Args:
            table: 表名

        Returns:
            是否成功
        """
        try:
            self._execute(f"DELETE FROM {table}", commit=True)
            self._execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'", commit=True)
            return True
        except sqlite3.Error as e:
            self.logger.error(f"Truncate table error: {e}")
            return False

    def create_index(
            self,
            table: str,
            columns: Union[str, List[str]],
            *,
            name: Optional[str] = None,
            unique: bool = False,
            if_not_exists: bool = True
    ) -> bool:
        """
        创建索引

        Args:
            table: 表名
            columns: 索引列
            name: 索引名
            unique: 是否唯一索引
            if_not_exists: 如果不存在则创建

        Returns:
            是否成功
        """
        if isinstance(columns, str):
            columns = [columns]

        if not name:
            col_str = "_".join(columns)
            name = f"idx_{table}_{col_str}"

        sql = "CREATE"
        if unique:
            sql += " UNIQUE"

        sql += " INDEX"
        if if_not_exists:
            sql += " IF NOT EXISTS"

        sql += f" {name} ON {table} ({', '.join(columns)})"

        try:
            self._execute(sql, commit=True)
            return True
        except sqlite3.Error as e:
            self.logger.error(f"Create index error: {e}")
            return False

    def table_exists(self, table: str) -> bool:
        """
        检查表是否存在

        Args:
            table: 表名

        Returns:
            是否存在
        """
        sql = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """
        result = self._execute(sql, (table,), fetch_one=True)
        return result is not None

    def get_table_info(self, table: str) -> List[Dict]:
        """
        获取表结构信息

        Args:
            table: 表名

        Returns:
            表结构信息
        """
        return self._execute(f"PRAGMA table_info({table})", fetch=True) or []

    # ========== JSON支持 ==========

    def json_insert(
            self,
            table: str,
            column: str,
            json_path: str,
            value: Any
    ) -> int:
        """
        插入JSON字段

        Args:
            table: 表名
            column: JSON列名
            json_path: JSON路径
            value: 值

        Returns:
            影响行数
        """
        sql = f"""
            UPDATE {table}
            SET {column} = json_insert({column}, ?, ?)
            WHERE id = ?
        """
        return self._execute(sql, (json_path, json.dumps(value)), commit=True) or 0

    def json_extract(
            self,
            table: str,
            column: str,
            json_path: str,
            *,
            as_type: str = "TEXT"
    ) -> List[Any]:
        """
        提取JSON字段

        Args:
            table: 表名
            column: JSON列名
            json_path: JSON路径
            as_type: 返回类型

        Returns:
            提取的值列表
        """
        sql = f"""
            SELECT json_extract({column}, ?) as value
            FROM {table}
            WHERE {column} IS NOT NULL
        """
        result = self._execute(sql, (json_path,), fetch=True) or []
        return [row["value"] for row in result]

    def json_set(
            self,
            table: str,
            column: str,
            json_path: str,
            value: Any,
            *,
            where: Optional[Dict] = None
    ) -> int:
        """
        设置JSON字段

        Args:
            table: 表名
            column: JSON列名
            json_path: JSON路径
            value: 值
            where: WHERE条件

        Returns:
            影响行数
        """
        sql = f"UPDATE {table} SET {column} = json_set({column}, ?, ?)"
        params = [json_path, json.dumps(value)]

        if where:
            where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
            sql += f" WHERE {where_clause}"
            params.extend(where.values())

        return self._execute(sql, params, commit=True) or 0

    # ========== 批量操作 ==========

    def bulk_upsert(
            self,
            table: str,
            data_list: List[Dict[str, Any]],
            conflict_fields: List[str],
            update_fields: Optional[List[str]] = None
    ) -> int:
        """
        批量插入或更新

        Args:
            table: 表名
            data_list: 数据列表
            conflict_fields: 冲突检测字段
            update_fields: 更新字段（None则更新所有非冲突字段）

        Returns:
            影响行数
        """
        if not data_list:
            return 0

        if not update_fields:
            # 获取所有非冲突字段
            all_fields = set(data_list[0].keys())
            update_fields = list(all_fields - set(conflict_fields))

        columns = list(data_list[0].keys())
        columns_str = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))

        update_clause = ", ".join([f"{col} = excluded.{col}" for col in update_fields])

        sql = f"""
            INSERT INTO {table} ({columns_str}) 
            VALUES ({placeholders})
            ON CONFLICT({', '.join(conflict_fields)}) 
            DO UPDATE SET {update_clause}
        """

        conn = self._get_connection()
        cursor = conn.cursor()
        total_rows = 0

        try:
            values = [tuple(row[col] for col in columns) for row in data_list]
            cursor.executemany(sql, values)
            total_rows = cursor.rowcount
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            self.logger.error(f"Bulk upsert error: {e}")
            raise
        finally:
            cursor.close()

        return total_rows

    # ========== 备份与恢复 ==========

    def backup(self, backup_path: Union[str, Path]) -> bool:
        """
        备份数据库

        Args:
            backup_path: 备份文件路径

        Returns:
            是否成功
        """
        try:
            backup_path = Path(backup_path)
            backup_path.parent.mkdir(parents=True, exist_ok=True)

            source = self._get_connection()
            dest = sqlite3.connect(backup_path)

            with dest:
                source.backup(dest)

            dest.close()
            self.logger.info(f"Database backed up to: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"Backup error: {e}")
            return False

    def restore(self, backup_path: Union[str, Path]) -> bool:
        """
        恢复数据库

        Args:
            backup_path: 备份文件路径

        Returns:
            是否成功
        """
        try:
            backup_path = Path(backup_path)
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")

            # 关闭现有连接
            if hasattr(self._thread_local, 'connection'):
                self._thread_local.connection.close()
                delattr(self._thread_local, 'connection')

            # 复制备份文件
            import shutil
            shutil.copy2(backup_path, self.db_path)

            self.logger.info(f"Database restored from: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"Restore error: {e}")
            return False

    # ========== 异步支持 ==========

    async def async_execute(
            self,
            sql: str,
            params: Union[Tuple, Dict, List] = None,
            *,
            fetch: bool = False,
            fetch_one: bool = False
    ) -> Union[List[Dict], Dict, int, None]:
        """
        异步执行SQL

        Args:
            sql: SQL语句
            params: 参数
            fetch: 是否获取所有结果
            fetch_one: 是否获取单个结果

        Returns:
            查询结果
        """
        if self._async_conn is None:
            self._async_conn = await aiosqlite.connect(
                self.db_path,
                timeout=self.timeout,  # 使用配置的超时
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            # 应用PRAGMA配置
            await self._async_conn.execute(f"PRAGMA foreign_keys = {'ON' if self.enable_foreign_keys else 'OFF'}")
            await self._async_conn.execute(f"PRAGMA journal_mode = {self.journal_mode}")
            await self._async_conn.execute(f"PRAGMA cache_size = {self.cache_size}")
            await self._async_conn.execute(f"PRAGMA synchronous = {self.synchronous}")

        async with self._async_conn.cursor() as cursor:
            if self.debug:
                self.logger.debug(f"Async SQL: {sql}, Params: {params}")

            if params:
                await cursor.execute(sql, params)
            else:
                await cursor.execute(sql)

            if fetch:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
            elif fetch_one:
                row = await cursor.fetchone()
                return dict(row) if row else None
            else:
                await self._async_conn.commit()
                if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    return cursor.rowcount
                elif sql.strip().upper().startswith("INSERT"):
                    return cursor.lastrowid

    # ========== 工具方法 ==========

    def execute_raw(self, sql: str, params=None) -> Any:
        """
        执行原生SQL

        Args:
            sql: SQL语句
            params: 参数

        Returns:
            执行结果
        """
        return self._execute(sql, params)

    def vacuum(self) -> bool:
        """清理数据库空间"""
        try:
            self._execute("VACUUM", commit=True)
            return True
        except sqlite3.Error as e:
            self.logger.error(f"Vacuum error: {e}")
            return False

    def get_size(self) -> int:
        """获取数据库文件大小（字节）"""
        if self.db_path == ":memory:":
            return 0

        try:
            return Path(self.db_path).stat().st_size
        except:
            return 0

    def close(self):
        """关闭数据库连接（仅关闭连接，不执行 WAL 检查点）"""
        if hasattr(self._thread_local, 'connection'):
            try:
                self._thread_local.connection.close()
            except:
                pass
            delattr(self._thread_local, 'connection')

        if self._async_conn:
            try:
                # 尝试关闭异步连接
                if asyncio.get_event_loop().is_running():
                    asyncio.create_task(self._async_conn.close())
                else:
                    asyncio.run(self._async_conn.close())
            except:
                pass
            self._async_conn = None

        try:
            self._executor.shutdown(wait=False)
        except:
            pass

        self.logger.info("Database connections closed")

    def close_safely(self):
        """
        安全关闭数据库并合并 WAL 文件（推荐方法）
        执行步骤：
        1. 关闭所有连接
        2. 创建新连接执行 PRAGMA wal_checkpoint(TRUNCATE) 合并 WAL 文件
        3. 关闭线程池

        Returns:
            bool: 是否成功关闭
        """
        import os
        import time

        try:
            # 步骤1：先关闭所有现有连接（确保没有挂起的写操作）
            if hasattr(self._thread_local, 'connection'):
                try:
                    self._thread_local.connection.close()
                except:
                    pass
                delattr(self._thread_local, 'connection')

            if self._async_conn:
                try:
                    # 尝试关闭异步连接
                    if asyncio.get_event_loop().is_running():
                        asyncio.create_task(self._async_conn.close())
                    else:
                        asyncio.run(self._async_conn.close())
                except:
                    pass
                self._async_conn = None

            # 等待一段时间，确保所有写操作完成
            time.sleep(0.5)

            # 步骤2：执行 WAL 检查点，合并 -wal 和 -shm 文件
            if self.db_path and self.db_path != ":memory:" and os.path.exists(self.db_path):
                try:
                    # 创建新连接来执行检查点
                    import sqlite3 as sqlite_sync

                    # 多次尝试执行检查点（确保所有更改都已写入）
                    for attempt in range(3):
                        checkpoint_conn = sqlite_sync.connect(self.db_path, timeout=10.0)
                        cursor = checkpoint_conn.cursor()

                        # 执行 WAL 检查点（TRUNCATE 模式会强制合并并删除 WAL 文件）
                        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        result = cursor.fetchone()

                        checkpoint_conn.commit()
                        checkpoint_conn.close()

                        self.logger.info(f"WAL checkpoint attempt {attempt + 1}: {result}")

                        # 如果检查点成功（0），则退出循环
                        if result and result[0] == 0:
                            self.logger.info("✅ WAL checkpoint completed successfully, database files merged")
                            break
                        else:
                            # 等待后重试
                            time.sleep(0.2)

                except Exception as e:
                    self.logger.warning(f"⚠️ WAL checkpoint failed (continuing close): {str(e)[:50]}")

            # 步骤3：关闭线程池
            try:
                self._executor.shutdown(wait=False)
            except:
                pass

            self.logger.info("✅ Database closed safely with WAL checkpoint")
            return True

        except Exception as e:
            self.logger.error(f"❌ Error during safe database close: {e}")
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_safely()

    def __del__(self):
        try:
            self.close_safely()
        except:
            pass


# ========== 使用示例 ==========
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    # 1. 创建数据库实例
    db = SQLiteDB("./test.db", debug=True)

    try:
        # 2. 创建表
        db.create_table(
            "users",
            {
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "username": "TEXT UNIQUE NOT NULL",
                "email": "TEXT",
                "age": "INTEGER",
                "metadata": "JSON DEFAULT '{}'",
                "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP"
            },
            indexes=[
                {"columns": ["username"], "unique": True},
                {"columns": ["email"]},
                {"columns": ["created_at"]}
            ]
        )

        # 3. 插入数据
        user_id = db.insert("users", {
            "username": "john_doe",
            "email": "john@example.com",
            "age": 25,
            "metadata": {"role": "admin", "settings": {"theme": "dark"}}
        })
        print(f"Inserted user ID: {user_id}")

        # 4. 批量插入
        users = [
            {"username": "alice", "email": "alice@example.com", "age": 30},
            {"username": "bob", "email": "bob@example.com", "age": 28},
            {"username": "charlie", "email": "charlie@example.com", "age": 35}
        ]
        db.insert_many("users", users)

        # 5. 查询数据
        # 使用查询构建器
        query = db.query("users") \
            .select("id", "username", "age") \
            .where("age", 25, ">") \
            .order_by("age", ascending=False) \
            .limit(10)

        results = db.execute_query(query)
        print("Query results:", results)

        # 6. 更新数据
        db.update("users", {"age": 26}, where={"username": "john_doe"})

        # 7. 事务操作
        with db.transaction():
            db.insert("users", {"username": "transaction_test", "email": "test@test.com"})
            db.update("users", {"age": 100}, where={"username": "transaction_test"})

        # 8. JSON操作
        db.json_set("users", "metadata", "$.role", "super_admin",
                    where={"username": "john_doe"})

        # 9. 聚合查询
        count = db.count("users", where={"age": {">": 25}})
        print(f"Users over 25: {count}")

        # 10. 批量更新
        db.bulk_upsert(
            "users",
            [
                {"username": "john_doe", "email": "john_new@example.com", "age": 27},
                {"username": "new_user", "email": "new@example.com", "age": 22}
            ],
            conflict_fields=["username"],
            update_fields=["email", "age"]
        )

        # 11. 获取表信息
        table_info = db.get_table_info("users")
        print("Table info:", table_info)

        # 12. 备份数据库
        db.backup("./backup/test_backup.db")

    finally:
        # 清理
        db.drop_table("users", if_exists=True)
        db.close()


if __name__ == "__main__":
    # 1. 创建数据库实例
    db = SQLiteDB("./配置文件_系统配置/ikun.db", debug=True)

    try:
        # ==================== 1. 执行 DDL（创建表） ====================
        create_sql = """
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            shop_abbr TEXT UNIQUE NOT NULL,
            browser_id TEXT UNIQUE NOT NULL,
            connect_status TEXT DEFAULT '未连接',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
        # 执行 DDL，无需获取结果
        db.execute_sql(create_sql)
        print("表创建成功")

        # ==================== 2. 执行 INSERT（插入数据） ====================
        insert_sql = """
        INSERT INTO shops (shop_name, shop_abbr, browser_id, connect_status)
        VALUES (?, ?, ?, ?)
        """
        # 插入单条，返回自增 ID
        shop_id = db.execute_sql(
            insert_sql,
            params=("Devineresse Delights", "DD", "b0ee0aa5c0264b44a3f2a675fc4d7195", "未连接"),
            fetch="none"  # 不获取结果，默认值可省略
        )
        print(f"插入店铺 ID: {shop_id}")

        # 批量插入
        batch_sql = """
        INSERT INTO shops (shop_name, shop_abbr, browser_id, connect_status)
        VALUES (?, ?, ?, ?)
        """
        shops_data = [
            ("Margarida", "M", "474bacde61ce4934a241275af7481be3", "已连接"),
            ("Hephzibah", "H", "c05d0c933c39461a81cbd17399dc2e16", "未连接"),
            ("Paperclip Palace", "PP", "45bd2c1f1fa04d16add3cd1ca28d56aa", "未连接")
        ]
        # 批量执行需用 executemany，这里封装一个辅助方法（可选）
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.executemany(batch_sql, shops_data)
        conn.commit()
        print(f"批量插入 {cursor.rowcount} 条数据")

        # ==================== 3. 执行 SELECT（查询数据） ====================
        # 3.1 查询所有数据
        select_all_sql = "SELECT * FROM shops WHERE connect_status = ?"
        shops = db.execute_sql(select_all_sql, params=("未连接",), fetch="fetch")
        print("未连接的店铺：", shops)

        # 3.2 查询单条数据
        select_one_sql = "SELECT * FROM shops WHERE shop_abbr = ?"
        shop = db.execute_sql(select_one_sql, params=("M",), fetch="fetch_one")
        print("单条店铺信息：", shop)

        # ==================== 4. 执行 UPDATE（更新数据） ====================
        update_sql = "UPDATE shops SET connect_status = ? WHERE browser_id = ?"
        affected_rows = db.execute_sql(update_sql, params=("已连接", "b0ee0aa5c0264b44a3f2a675fc4d7195"))
        print(f"更新 {affected_rows} 条数据")

        # ==================== 5. 执行 DELETE（删除数据） ====================
        delete_sql = "DELETE FROM shops WHERE shop_abbr = ?"
        affected_rows = db.execute_sql(delete_sql, params=("PP",))
        print(f"删除 {affected_rows} 条数据")

        # ==================== 6. 执行复杂 SQL（聚合查询） ====================
        count_sql = "SELECT connect_status, COUNT(*) as total FROM shops GROUP BY connect_status"
        count_result = db.execute_sql(count_sql, fetch="fetch")
        print("连接状态统计：", count_result)

    finally:
        # 清理
        db.execute_sql("DROP TABLE IF EXISTS shops")
        db.close()

from datetime import datetime, timedelta, timezone

def timestamp_to_datetime_str(timestamp: float) -> str:
    """
    转换时间戳为 SQLite 东8区时间字符串（和 datetime('now', '+8 hours') 一致）
    """
    # 使用带UTC时区的fromtimestamp（推荐写法）
    utc_dt = datetime.fromtimestamp(timestamp, timezone.utc)
    # 东8区时区对象（替代手动加8小时，更规范）
    beijing_tz = timezone(timedelta(hours=8))
    # 转换为东8区时间
    beijing_dt = utc_dt.astimezone(beijing_tz)
    # 格式化为SQLite兼容的字符串
    return beijing_dt.strftime("%Y-%m-%d %H:%M:%S")
