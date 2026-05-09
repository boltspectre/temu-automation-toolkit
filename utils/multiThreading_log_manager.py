import os
import time
import hashlib
import importlib
import json
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Callable, Set
from queue import Queue, Empty, Full

from loguru import logger

from config.common_config import db, config_manager, max_concurrent_tasks as max_concurrent_tasks_config
from config.middleware_config import task_concurrent_config

# ===================== 核心修复：全局日志锁 + 防止sink重复注册 =====================
LOG_LOCK = threading.Lock()
SINK_REGISTERED = False  # 标记sink是否已注册

TOTAL_LOG_FILE = "./total_log.txt"

# 任务状态（中文枚举）
class TaskStatus:
    PENDING = "待处理"  # 待执行
    RUNNING = "进行中"  # 执行中
    SUCCESS = "已完成"  # 执行成功
    FAILED = "异常"     # 执行失败
    TIMEOUT = "已超时"  # 执行超时
    STOPPED = "已退出"  # 主动终止

# 新增：任务管理器工作模式（初始化指定，全局生效）
class TaskManagerMode:
    ACTIVE = "active"    # 主动模式：自行从数据库拾取任务（原逻辑）
    PASSIVE = "passive"  # 被动模式：从中心化分配线程接收任务，不主动查询

@dataclass
class TaskInfo:
    """任务信息数据类"""
    task_id: str
    func_name: str  # 仅用于日志/展示
    func_path: str  # 函数完整路径，用于动态导入
    task_group: str
    task_name: Optional[str] = None  # 主任务记录，子任务为None
    status: str = TaskStatus.PENDING
    msg: Optional[str] = None
    remarks: Optional[str] = None
    mall_id: Optional[int] = None
    is_main_task: int = 0  # 0=子任务，1=主任务
    parent_task_id: Optional[str] = None
    log: str = ""
    create_time: float = field(default_factory=time.time)
    update_time: float = field(default_factory=time.time)


# 全局变量（移除了TASK_FUNC_MAP相关）
THREAD_TASK_MAP = {}
THREAD_TASK_LOCK = threading.RLock()  # 改为可重入锁
TASK_EXECUTING_FLAG = {}  # 标记任务是否正在执行，防止重复启动
EXECUTING_FLAG_LOCK = threading.RLock()

TASK_TYPE_NAME_MAP = {
    "1": "上传实拍图",
    "2": "核价"
}


def get_func_full_name(func: Callable) -> str:
    """获取函数的完整名称（模块+函数名），用于存储和动态导入"""
    return f"{func.__module__}.{func.__name__}"


def generate_unique_task_id(target_func: Callable, task_kwargs: dict, mall_id: int,
                            task_name: str = "", parent_task_id: str = "") -> str:
    """
    生成唯一task_id（兼容主/子任务）
    :param target_func: 函数对象
    :param task_kwargs: 函数参数
    :param mall_id: 商城ID
    :param task_name: 主任务类型（子任务为空）
    :param parent_task_id: 父任务ID
    :return: 32位MD5
    """
    def clean_kwargs(kwargs):
        clean = {}
        for k, v in kwargs.items():
            try:
                json.dumps(v)
                clean[k] = v
            except:
                clean[k] = str(v)
        return clean

    func_name = get_func_full_name(target_func)
    sorted_kwargs = json.dumps(clean_kwargs(task_kwargs), sort_keys=True, ensure_ascii=False)
    raw_str = f"{task_name}_{func_name}_{sorted_kwargs}_{mall_id or 0}_{parent_task_id}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()


def import_function_from_path(func_path: str) -> Optional[Callable]:
    """从函数完整路径动态导入函数对象"""
    try:
        if "." not in func_path:
            logger.error(f"函数路径格式错误 | 路径: {func_path}")
            return None

        module_path, func_name = func_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)

        if callable(func):
            return func
        else:
            logger.error(f"路径 {func_path} 对应的不是可调用对象")
            return None
    except (ValueError, ImportError, AttributeError) as e:
        logger.error(f"动态导入函数失败 | 路径: {func_path} | 错误: {e}")
        return None


class TaskLogManager:
    """通用任务管理器（多进程兼容 + 主动/被动双模式 + 中心化分配基础）"""
    # 进程内单例控制属性
    _instance = None
    _process_pid = None
    _init_lock = threading.Lock()

    def __new__(cls, max_concurrent_tasks=None, task_timeout=3600, poll_interval=5,
                mode: str = TaskManagerMode.ACTIVE):
        current_pid = os.getpid()
        if cls._instance is None or cls._process_pid != current_pid:
            with cls._init_lock:
                if cls._instance is None or cls._process_pid != current_pid:
                    cls._instance = super().__new__(cls)
                    cls._process_pid = current_pid
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_concurrent_tasks=None, task_timeout=3600, poll_interval=5,
                 mode: str = TaskManagerMode.ACTIVE):
        """
        初始化任务管理器（新增双模式支持）
        :param max_concurrent_tasks: 全局最大并发数，如果为None则从配置文件读取
        :param task_timeout: 单个任务超时时间（秒）
        :param poll_interval: 主动模式下的轮询间隔（秒）
        :param mode: 工作模式 - TaskManagerMode.ACTIVE/TaskManagerMode.PASSIVE
        """
        # 如果未指定max_concurrent_tasks，则从配置文件读取
        if max_concurrent_tasks is None:
            max_concurrent_tasks = max_concurrent_tasks_config
        if getattr(self, '_initialized', True):
            return

        # 新增：初始化工作模式（强制校验合法性）
        self.mode = mode if mode in [TaskManagerMode.ACTIVE, TaskManagerMode.PASSIVE] else TaskManagerMode.ACTIVE
        # 新增：被动模式专用线程安全队列（接收中心化分配的任务，最大容量=全局最大并发）
        self._passive_task_queue = Queue(maxsize=max_concurrent_tasks)
        # 新增：已接收任务去重集合（防止中心化分配重复任务）
        self._received_task_ids: Set[str] = set()
        
        # 定时任务执行器
        self.scheduled_task_executor = None
        self._received_task_lock = threading.RLock()

        # 原初始化逻辑完全保留
        self.db = db
        self.db.execute_sql("PRAGMA journal_mode=WAL")
        self.db.execute_sql("PRAGMA cache_size=-20000")
        self.db.execute_sql("PRAGMA synchronous=NORMAL")

        self.global_max_concurrent = max_concurrent_tasks
        self.task_timeout = task_timeout
        self.poll_interval = poll_interval
        
        # 确保使用最新的task_concurrent_config
        from config.common_config import task_concurrent_config as latest_task_concurrent_config
        self.func_concurrent_config = latest_task_concurrent_config

        self._global_semaphore = threading.Semaphore(max_concurrent_tasks)
        self._group_semaphores: Dict[str, threading.Semaphore] = {}
        self._group_sem_lock = threading.RLock()

        self._stop_flag = threading.Event()
        self._lock = threading.RLock()
        self._task_poll_lock = threading.RLock()
        self.running_tasks: Dict[str, threading.Thread] = {}

        self._init_loguru_sink()
        self.clean_all_unfinished_subtasks_on_start()

        # 启动任务拾取轮询线程（改造后适配双模式）
        self._poll_thread = threading.Thread(target=self._task_polling, daemon=True, name="task_poll_thread")
        self._poll_thread.start()

        self._initialized = True

        # 启动日志（标记工作模式）
        with LOG_LOCK:
            logger.info(
                f"任务管理器初始化完成 | 工作模式: {self.mode.upper()} | 进程PID: {os.getpid()} "
                f"| 全局最大并发: {self.global_max_concurrent} | 轮询间隔: {self.poll_interval}秒"
            )

    # ===================== 新增核心：双模式任务获取统一接口 + 被动接收方法 =====================
    def _get_pending_tasks(self) -> List[Dict]:
        """
        统一任务获取接口（核心：根据工作模式分发）
        :return: 待处理任务列表（task_id为主键）
        """
        if self.mode == TaskManagerMode.ACTIVE:
            # 主动模式：原逻辑，从数据库拾取任务（加锁+限制数量）
            with self._task_poll_lock:
                pending_tasks = self.db.execute_sql(
                    """
                    SELECT task_id
                    FROM task
                    WHERE status = ? LIMIT ?
                    """,
                    params=[TaskStatus.PENDING, min(10, self.global_max_concurrent - len(self.running_tasks))],
                    fetch="fetch"
                )
            return pending_tasks or []
        else:
            # 被动模式：从中心化分配的队列中获取任务（阻塞超时1秒，避免死等）
            pending_tasks = []
            try:
                # 一次获取最多5个任务（可配置），防止单批次处理过多
                for _ in range(min(5, self.global_max_concurrent - len(self.running_tasks))):
                    task_id = self._passive_task_queue.get(block=True, timeout=1)
                    # 去重校验 + 状态二次校验
                    with self._received_task_lock:
                        if task_id in self._received_task_ids:
                            self._passive_task_queue.task_done()
                            continue
                        self._received_task_ids.add(task_id)
                    # 校验任务是否为待处理状态
                    task_status = self.db.execute_sql(
                        "SELECT task_id, status FROM task WHERE task_id = ?",
                        params=[task_id],
                        fetch="fetch_one"
                    )
                    if task_status and task_status["status"] == TaskStatus.PENDING:
                        pending_tasks.append({"task_id": task_id})
                    self._passive_task_queue.task_done()
            except Empty:
                # 队列为空，正常返回空列表
                pass
            except Exception as e:
                with LOG_LOCK:
                    logger.error(f"被动模式获取任务异常 | 错误: {e}", exc_info=True)
            return pending_tasks

    def passive_receive_task(self, task_id: str) -> bool:
        """
        被动模式接收中心化分配的任务（供外部分配线程调用）
        :param task_id: 分配的任务ID
        :return: True=接收成功，False=接收失败（队列满/任务已存在/状态异常）
        """
        if self.mode != TaskManagerMode.PASSIVE:
            with LOG_LOCK:
                logger.warning(f"非被动模式拒绝接收任务 | task_id: {task_id} | 当前模式: {self.mode}")
            return False

        try:
            # === 关键修复：原子抢占任务 ===
            # 只有当前状态是 PENDING，才更新为 RUNNING
            rows_affected = self.db.execute_sql(
                "UPDATE task SET status = ? WHERE task_id = ? AND status = ?",
                params=[TaskStatus.RUNNING, task_id, TaskStatus.PENDING],
                fetch="none"
            )

            if rows_affected == 0:
                # 说明任务不是 PENDING（可能已被其他进程抢走，或已完成）
                task_info = self.db.execute_sql(
                    "SELECT status FROM task WHERE task_id = ?",
                    params=[task_id],
                    fetch="fetch_one"
                )
                current_status = task_info["status"] if task_info else "NOT_FOUND"
                with LOG_LOCK:
                    logger.warning(f"任务状态异常，拒绝接收 | task_id: {task_id} | 状态: {current_status}")
                return False

            # === 抢占成功，放入队列 ===
            self._passive_task_queue.put(task_id, block=False)
            with LOG_LOCK:
                logger.debug(
                    f"被动模式接收任务成功 | task_id: {task_id} | 队列剩余容量: {self._passive_task_queue.maxsize - self._passive_task_queue.qsize()}")
            return True

        except Full:
            # 注意：此时任务已在 DB 中标记为 RUNNING，但未被处理！
            # 这是个危险状态，需要回滚或由监控恢复
            with LOG_LOCK:
                logger.error(f"队列满，但任务已标记为RUNNING！需人工干预或自动恢复 | task_id: {task_id}")
            # 可选：回滚状态（但可能引发新问题）
            # self.db.execute_sql("UPDATE task SET status = ? WHERE task_id = ?", [TaskStatus.PENDING, task_id])
            return False

        except Exception as e:
            with LOG_LOCK:
                logger.error(f"被动模式接收任务异常 | task_id: {task_id} | 错误: {e}", exc_info=True)
            return False

    # ===================== 改造核心：_task_polling 适配双模式统一接口 =====================
    def _task_polling(self):
        """任务拾取轮询（改造后：基于统一接口，适配主动/被动双模式）"""
        with LOG_LOCK:
            logger.info(
                f"任务拾取轮询启动 | 工作模式: {self.mode.upper()} | 轮询间隔: {self.poll_interval}秒"
            )

        while not self._stop_flag.is_set():
            try:
                self._cleanup_orphaned_tasks()

                # 核心改造：调用统一任务获取接口，屏蔽模式差异
                pending_tasks = self._get_pending_tasks()
                if not pending_tasks:
                    # 主动模式：按配置轮询间隔休眠
                    # 被动模式：短休眠（1秒），快速响应队列任务
                    sleep_time = self.poll_interval if self.mode == TaskManagerMode.ACTIVE else 1
                    time.sleep(sleep_time)
                    continue

                # 原有任务处理逻辑完全保留（无需修改）
                for task in pending_tasks:
                    task_id = task["task_id"]

                    # 双重校验：防止重复启动
                    with self._lock:
                        if task_id in self.running_tasks:
                            continue
                    with EXECUTING_FLAG_LOCK:
                        if TASK_EXECUTING_FLAG.get(task_id, False):
                            continue

                    # 二次校验状态（加锁查询）
                    with self._lock:
                        current_status = self.db.execute_sql(
                            "SELECT status FROM task WHERE task_id = ?",
                            params=[task_id],
                            fetch="fetch_one"
                        )["status"]
                        if current_status != TaskStatus.PENDING:
                            # 被动模式：清理去重集合
                            if self.mode == TaskManagerMode.PASSIVE:
                                with self._received_task_lock:
                                    self._received_task_ids.discard(task_id)
                            continue

                    # 启动任务线程
                    task_thread = threading.Thread(
                        target=self._execute_task,
                        args=(task_id,),
                        name=f"task_thread_{task_id}",
                        daemon=True
                    )
                    task_thread.start()

                    # 标记为运行中
                    with self._lock:
                        self.running_tasks[task_id] = task_thread

            except Exception as e:
                with LOG_LOCK:
                    logger.error(f"任务轮询异常 | 工作模式: {self.mode} | 原因: {e}", exc_info=True)
                # 异常后休眠，避免高频报错
                time.sleep(self.poll_interval if self.mode == TaskManagerMode.ACTIVE else 1)

    # ===================== 原有方法完全保留（无任何修改）=====================
    def clean_all_unfinished_subtasks_on_start(self):
        """启动时清理未完成子任务+修正状态+主任务去重"""
        try:
            running_tasks = self.db.execute_sql(
                """SELECT task_id FROM task where status = ? or status = ?""",
                params=[TaskStatus.RUNNING, TaskStatus.PENDING],
                fetch="fetch"
            )
            if running_tasks:
                for task_id in [t["task_id"] for t in running_tasks]:
                    self.update_task_field(
                        task_id,
                        status=TaskStatus.STOPPED,
                        msg="退出或重启时任务自动终止",
                        remarks=f"任务管理器退出或重启，任务自动退出 | 更新时间: {datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}"
                    )

            self.db.execute_sql("DELETE FROM task WHERE is_main_task = 0", params=[], fetch="none")

            main_tasks = self.db.execute_sql(
                """SELECT task_id, func_path, task_kwargs, mall_id, task_name FROM task WHERE is_main_task = 1""",
                params=[],
                fetch="fetch"
            )
            main_task_unique_map = {}
            duplicate_main_task_ids = []
            for main_task in main_tasks:
                unique_key = (
                    main_task["func_path"],
                    main_task["task_kwargs"],
                    main_task["mall_id"] or 0,
                    main_task["task_name"] or ""
                )
                if unique_key in main_task_unique_map:
                    duplicate_main_task_ids.append(main_task["task_id"])
                    with LOG_LOCK:
                        logger.warning(f"发现重复主任务，即将清理 | task_id: {main_task['task_id']} | 重复key: {unique_key}")
                else:
                    main_task_unique_map[unique_key] = main_task["task_id"]
            for duplicate_task_id in duplicate_main_task_ids:
                self.update_task_field(
                    duplicate_task_id,
                    status=TaskStatus.STOPPED,
                    msg="重复主任务被清理",
                    remarks="任务管理器启动时检测到重复主任务（同一函数+参数），自动清理"
                )
        except Exception as e:
            with LOG_LOCK:
                logger.error(f"启动时清理失败 | 错误: {e}", exc_info=True)

    def _get_main_task_id(self, task_id: str) -> str:
        """递归获取任务的根主任务ID"""
        try:
            task_info = self.db.execute_sql(
                "SELECT is_main_task, parent_task_id FROM task WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            if not task_info:
                return task_id
            if task_info["is_main_task"] == 1:
                return task_id
            parent_id = task_info["parent_task_id"]
            if not parent_id:
                return task_id
            return self._get_main_task_id(parent_id)
        except Exception as e:
            logger.error(f"获取主任务ID失败 | task_id: {task_id} | 错误: {e}")
            return task_id

    def _loguru_task_sink(self, message):
        """Loguru自定义sink：将任务线程日志写入数据库"""
        record = message.record
        thread_id = record["thread"].id
        task_info = THREAD_TASK_MAP.get(thread_id, {})
        task_id = task_info.get("task_id")
        task_group = task_info.get("task_group")
        if not task_id or not task_group:
            return
        target_task_id = self._get_main_task_id(task_id)
        log_content = (
            f"{record['time'].strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{record['level'].name} | {record['message']}\n"
        )
        try:
            with self._lock:
                current_log = self.db.execute_sql(
                    "SELECT log FROM task WHERE task_id = ?",
                    params=[target_task_id],
                    fetch="fetch_one"
                )
                current_log_str = current_log["log"] if (current_log and current_log["log"]) else ""
                new_log = current_log_str + log_content
                self.db.execute_sql(
                    """UPDATE task SET log = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?""",
                    params=[new_log, target_task_id],
                    fetch="none"
                )
        except Exception as e:
            logger.error(f"日志写入数据库失败 | task_id: {target_task_id} | 错误: {e}")

    def _loguru_group_filter(self, record) -> bool:
        """Loguru过滤器：筛选任务线程日志"""
        with THREAD_TASK_LOCK:
            task_info = THREAD_TASK_MAP.get(record["thread"].id, {})
        return bool(task_info.get("task_id") and task_info.get("task_group"))

    def _init_loguru_sink(self):
        """初始化Loguru：防止sink重复注册"""
        global SINK_REGISTERED
        with LOG_LOCK:
            if not SINK_REGISTERED:
                logger.add(
                    self._loguru_task_sink,
                    filter=self._loguru_group_filter,
                    level="TRACE",
                )
                SINK_REGISTERED = True

    def update_task_field(self, task_id: str, **fields):
        """更新任务指定字段（加锁保证线程安全）"""
        if not fields:
            return
        with self._lock:
            field_str = ", ".join([f"{k} = ?" for k in fields.keys()])
            params = list(fields.values()) + [task_id]
            if "update_time" not in fields:
                field_str += ", update_time = datetime('now', '+8 hours')"
            sql = f"UPDATE task SET {field_str} WHERE task_id = ?"
            self.db.execute_sql(sql, params=params, fetch="none")

    def update_task_msg(self, task_id: str, msg: str):
        """专门更新任务msg字段"""
        if not task_id or not msg:
            logger.warning(f"更新task msg失败 | task_id为空或msg为空 | task_id: {task_id} | msg: {msg}")
            return
        self.update_task_field(task_id, msg=msg)

    def update_task_remarks(self, task_id: str, remarks: str, append: bool = False):
        """专门更新任务remarks字段（支持追加/覆盖）"""
        if not task_id or not remarks:
            logger.warning(f"更新task remarks失败 | task_id为空或remarks为空 | task_id: {task_id} | remarks: {remarks}")
            return
        if append:
            try:
                with self._lock:
                    current_remarks = self.db.execute_sql(
                        "SELECT remarks FROM task WHERE task_id = ?",
                        params=[task_id],
                        fetch="fetch_one"
                    )
                current_remarks_str = current_remarks["remarks"] if (current_remarks and current_remarks["remarks"]) else ""
                timestamp = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                new_remarks = f"{current_remarks_str} {remarks} [更新时间：{timestamp}] " if current_remarks_str else f"{remarks} [更新时间：{timestamp}]"
            except Exception as e:
                logger.error(f"读取原有remarks失败，改为覆盖模式 | task_id: {task_id} | 错误: {e}")
                new_remarks = remarks
        else:
            new_remarks = remarks
        self.update_task_field(task_id, remarks=new_remarks)

    def update_task_msg_and_remarks(self, task_id: str, msg: str, remarks: str, remarks_append: bool = False):
        """批量更新msg和remarks字段（一次数据库操作，效率更高）"""
        if not task_id or (not msg and not remarks):
            logger.warning(f"批量更新msg/remarks失败 | 参数无效 | task_id: {task_id} | msg: {msg} | remarks: {remarks}")
            return
        update_fields = {}
        if msg:
            update_fields["msg"] = msg
        if remarks:
            if remarks_append:
                try:
                    with self._lock:
                        current_remarks = self.db.execute_sql(
                            "SELECT remarks FROM task WHERE task_id = ?",
                            params=[task_id],
                            fetch="fetch_one"
                        )
                    current_remarks_str = current_remarks["remarks"] if (current_remarks and current_remarks["remarks"]) else ""
                    timestamp = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    new_remarks = f"{current_remarks_str}\n[{timestamp}] {remarks}" if current_remarks_str else f"[{timestamp}] {remarks}"
                    update_fields["remarks"] = new_remarks
                except Exception as e:
                    logger.error(f"读取原有remarks失败，改为覆盖模式 | task_id: {task_id} | 错误: {e}")
                    update_fields["remarks"] = remarks
            else:
                update_fields["remarks"] = remarks
        self.update_task_field(task_id, **update_fields)

    def _clean_sub_tasks(self, parent_task_id: str) -> tuple[bool, str]:
        """清理指定父任务下的所有子任务"""
        try:
            sub_tasks = self.db.execute_sql(
                """SELECT task_id FROM task WHERE parent_task_id = ? AND status NOT IN (?, ?, ?, ?)""",
                params=[parent_task_id, TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT, TaskStatus.STOPPED],
                fetch="fetch"
            )
            if not sub_tasks:
                return True, "无待清理的子任务"
            sub_task_ids = [t["task_id"] for t in sub_tasks]
            logger.info(f"开始清理子任务 | 父任务: {parent_task_id} | 数量: {len(sub_task_ids)}")
            for sub_task_id in sub_task_ids:
                self.update_task_field(
                    sub_task_id,
                    status=TaskStatus.STOPPED,
                    msg="子任务被清理",
                    remarks=f"父任务{parent_task_id}重新执行/启动清理，清理子任务"
                )
            with self._lock:
                for sub_task_id in sub_task_ids:
                    if sub_task_id in self.running_tasks:
                        self.running_tasks[sub_task_id].join(timeout=1)
                        del self.running_tasks[sub_task_id]
            success_msg = f"成功标记 {len(sub_task_ids)} 个子任务为{TaskStatus.STOPPED}"
            logger.info(success_msg)
            return True, success_msg
        except Exception as e:
            error_msg = f"清理子任务异常：{str(e)}"
            logger.error(error_msg, exc_info=True)
            self.update_task_field(parent_task_id, msg="清理子任务失败", remarks=error_msg)
            return False, error_msg

    def add_task(self,
                 target_func: Callable,
                 task_id: Optional[str] = None,
                 task_group: str = "",
                 mall_id: Optional[int] = None,
                 task_name: Optional[str] = None,
                 parent_task_id: Optional[str] = None,
                 is_main_task: int = 0, **kwargs):
        """添加任务（完全基于数据库，无内存缓存）"""
        if not task_id:
            task_id = generate_unique_task_id(target_func, kwargs, mall_id or 0, task_name or "", parent_task_id or "")
        func_path = get_func_full_name(target_func)
        func_name = func_path
        if is_main_task == 1:
            self._clean_sub_tasks(task_id)
        task_kwargs_str = json.dumps(kwargs, ensure_ascii=False)
        task_data = {
            "task_id": task_id,
            "func_name": func_name,
            "func_path": func_path,
            "task_name": task_name,
            "task_group": task_group,
            "status": TaskStatus.PENDING,
            "msg": f"任务已创建 | 任务类型: {task_name if task_name else '子任务'}",
            "remarks": "",
            "mall_id": mall_id,
            "is_main_task": is_main_task,
            "parent_task_id": parent_task_id,
            "task_kwargs": task_kwargs_str,
            "log": "",
        }
        fields = list(task_data.keys())
        placeholders = ", ".join(["?"] * len(fields))
        sql = f"INSERT OR REPLACE INTO task ({', '.join(fields)}) VALUES ({placeholders})"
        self.db.execute_sql(sql, params=list(task_data.values()), fetch="none")
        with LOG_LOCK:
            logger.info(
                f"任务创建成功 | task_id: {task_id} | 分组: {task_group} | 主任务: {is_main_task == 1} | 任务名称: {task_name if task_name else '子任务'} | 函数路径: {func_path}"
            )
        return task_id

    def _parse_group_name(self, group_name: str) -> tuple:
        """解析分组名，返回 (店铺名, 功能名)"""
        parts = group_name.split("_", 1)
        if len(parts) != 2:
            return "全局", "全局任务"
        return parts[0], parts[1]

    def _get_group_semaphore(self, group_name: str) -> threading.Semaphore:
        """获取分组并发信号量（实时检查配置，动态更新）"""
        with self._group_sem_lock:
            shop_name, func_name = self._parse_group_name(group_name)
            new_max = self.func_concurrent_config.get(func_name, self.func_concurrent_config.get("default", 200))
            if group_name in self._group_semaphores:
                sem = self._group_semaphores[group_name]
                current_used = (getattr(sem, "_max_value", new_max)) - sem._value
                if getattr(sem, "_max_value", 0) != new_max:
                    new_sem = threading.Semaphore(new_max)
                    for _ in range(min(current_used, new_max)):
                        new_sem.acquire(blocking=False)
                    self._group_semaphores[group_name] = new_sem
                    new_sem._max_value = new_max
                    logger.info(
                        f"更新分组信号量 | 分组: {group_name} | 功能: {func_name} "
                        f"| 旧最大数: {getattr(sem, '_max_value', 0)} → 新最大数: {new_max} "
                        f"| 已使用数: {current_used} → 新已使用数: {min(current_used, new_max)}"
                    )
                    return new_sem
                return sem
            sem = threading.Semaphore(new_max)
            sem._max_value = new_max
            self._group_semaphores[group_name] = sem
            logger.info(
                f"初始化分组信号量 | 分组: {group_name} | 店铺: {shop_name} | 功能: {func_name} | 最大并发: {new_max}")
            return sem

    def update_func_config(self, func_name: str, max_concurrent: int):
        """动态更新功能并发配置（修改后立即生效）"""
        with self._group_sem_lock:
            old_max = self.func_concurrent_config.get(func_name, self.func_concurrent_config["default"])
            self.func_concurrent_config[func_name] = max_concurrent
            for group_name in list(self._group_semaphores.keys()):
                _, group_func = self._parse_group_name(group_name)
                if group_func == func_name:
                    self._get_group_semaphore(group_name)
        logger.info(f"更新功能并发配置 | 功能: {func_name} | 旧值: {old_max} → 新值: {max_concurrent}（已实时生效）")

    def _execute_task(self, task_id: str):
        """执行单个任务（从数据库读取函数路径和参数，动态导入执行）"""
        global THREAD_TASK_MAP, TASK_EXECUTING_FLAG
        thread_id = threading.current_thread().ident
        thread_name = threading.current_thread().name
        with EXECUTING_FLAG_LOCK:
            if TASK_EXECUTING_FLAG.get(task_id, False):
                logger.warning(f"任务已在执行中，跳过 | task_id: {task_id} | 线程: {thread_name}")
                return
            TASK_EXECUTING_FLAG[task_id] = True
        try:
            task_info_db = self.db.execute_sql(
                "SELECT * FROM task WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            if not task_info_db:
                logger.warning(f"任务不存在 | task_id: {task_id}")
                return
            if task_info_db["status"] != TaskStatus.PENDING:
                return
            task_group = task_info_db["task_group"]
            with THREAD_TASK_LOCK:
                THREAD_TASK_MAP[thread_id] = {"task_id": task_id, "task_group": task_group}
            
            # 权限校验
            task_name = task_info_db.get("task_name", "")
            if task_name:
                # 使用统一的权限管理器检查权限
                from config.permission_manager import permission_manager
                if not permission_manager.check_permission(task_name):
                    self.update_task_field(
                        task_id,
                        status=TaskStatus.FAILED,
                        msg="权限不足",
                        remarks=f"您没有执行此任务的权限: {task_name}"
                    )
                    logger.warning(f"任务执行被拒绝，权限不足 | task_id: {task_id} | task_name: {task_name}")
                    return
            
            self.update_task_field(task_id, status=TaskStatus.RUNNING, msg="任务执行中")
            with LOG_LOCK:
                logger.info(f"任务执行中 | task_id: {task_id} | 线程: {thread_name}")
            func_path = task_info_db.get("func_path")
            task_kwargs_str = task_info_db.get("task_kwargs", "{}")
            if not func_path:
                error_msg = f"函数路径为空 | task_id: {task_id}"
                self.update_task_field(task_id, status=TaskStatus.FAILED, msg="执行失败", remarks=error_msg)
                logger.error(error_msg)
                return
            target_func = import_function_from_path(func_path)
            if not target_func or not callable(target_func):
                error_msg = f"动态导入函数失败 | task_id: {task_id} | 函数路径: {func_path}"
                self.update_task_field(task_id, status=TaskStatus.FAILED, msg="执行失败", remarks=error_msg)
                logger.error(error_msg)
                return
            try:
                task_kwargs = json.loads(task_kwargs_str)
            except json.JSONDecodeError as e:
                error_msg = f"解析任务参数失败 | task_id: {task_id} | 错误: {e}"
                self.update_task_field(task_id, status=TaskStatus.FAILED, msg="执行失败", remarks=error_msg)
                logger.error(error_msg)
                return
            group_sem = self._get_group_semaphore(task_group)
            self._global_semaphore.acquire()
            group_sem.acquire()
            shop_name, func_name = self._parse_group_name(task_group)
            global_used = self.global_max_concurrent - self._global_semaphore._value
            group_max = self.func_concurrent_config.get(func_name, self.func_concurrent_config["default"])
            group_used = group_max - group_sem._value
            logger.info(
                f"任务并发信息 | task_id: {task_id} | 店铺: {shop_name} | 功能: {func_name} "
                f"| 全局并发: {global_used}/{self.global_max_concurrent} "
                f"| 功能并发: {group_used}/{group_max}"
            )
            try:
                result = target_func(**task_kwargs)
                # 统一结果格式处理，强制封装为JSON可解析的标准格式
                if isinstance(result, dict) and "code" in result:
                    code = result.get("code")
                    remarks = result.get("remarks", "")
                    msg = result.get("msg", "任务执行完成")
                    data = result.get("data", {})
                    # 封装标准执行结果，确保可JSON解析，避免非字符串类型报错
                    # standard_remarks = f"执行结果a: {json.dumps(result, ensure_ascii=False)} | 业务备注: {remarks}"
                    standard_remarks = f"{remarks}"

                else:
                    # 非标准返回格式，自动封装为标准格式
                    code = 1
                    msg = "任务完成，非标准返回格式"
                    default_result = {"code": 1, "msg": msg, "data": result, "remarks": "非标准返回自动封装"}
                    standard_remarks = f"执行结果: {json.dumps(default_result, ensure_ascii=False)} | 业务备注: 原返回：{str(result)[:200]}"


                if code == 1:
                    self.update_task_field(
                        task_id,
                        status=TaskStatus.SUCCESS,
                        msg=msg,
                        remarks=standard_remarks
                    )
                else:
                    print("msg", msg, standard_remarks)
                    if "验证码输入框" in standard_remarks:
                        self.update_task_field(
                            task_id,
                            status="验证码",
                            msg=msg or "任务执行失败",
                            remarks=standard_remarks
                        )
                    else:
                        self.update_task_field(
                            task_id,
                            status=TaskStatus.FAILED,
                            msg=msg or "任务执行失败",
                            remarks=standard_remarks
                        )
                with LOG_LOCK:
                    logger.info(
                        f"任务执行完成 | task_id: {task_id} | 执行状态: 成功" if code == 1 else f"任务执行完成 | task_id: {task_id} | 执行状态: 失败")
            except TimeoutError as e:
                # 超时异常单独处理，标记为超时状态
                error_result = {"code": -2, "msg": "任务执行超时", "data": {}, "remarks": str(e)}
                # error_remarks = f"执行结果: {json.dumps(error_result, ensure_ascii=False)} | 业务备注: 超时原因：{str(e)}"
                error_remarks = f"业务备注: 超时原因：{str(e)}"


                self.update_task_field(task_id, status=TaskStatus.TIMEOUT, msg="执行超时", remarks=error_remarks)
                logger.error(f"任务执行超时 | task_id: {task_id} | 原因: {e}", exc_info=True)
            except Exception as e:
                # 全局异常捕获，统一封装错误信息，避免直接抛出非字符串类型
                # error_result = {"code": -1, "msg": "任务执行异常", "data": {}, "remarks": str(e),
                #                 "traceback": traceback.format_exc()[:500]}
                error_remarks = f"原因：{str(e)[:200]}"

                self.update_task_field(task_id, status=TaskStatus.FAILED, msg="执行失败", remarks=error_remarks)
                logger.error(f"任务执行失败 | task_id: {task_id} | 原因: {e}", exc_info=True)
            finally:
                # 确保信号量无论是否异常都能释放，避免死锁
                group_sem.release()
                self._global_semaphore.release()
        except Exception as e:
            logger.error(f"任务执行框架异常 | task_id: {task_id} | 错误: {e}", exc_info=True)
        finally:
            # 最终清理，确保标记和映射关系被移除
            with EXECUTING_FLAG_LOCK:
                if task_id in TASK_EXECUTING_FLAG:
                    del TASK_EXECUTING_FLAG[task_id]
            with THREAD_TASK_LOCK:
                if thread_id in THREAD_TASK_MAP:
                    del THREAD_TASK_MAP[thread_id]
            with self._lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
            # 被动模式：任务执行完成后清理去重集合
            if self.mode == TaskManagerMode.PASSIVE:
                with self._received_task_lock:
                    self._received_task_ids.discard(task_id)

    def get_task_result(self, task_id, timeout=None, poll_interval=0.5):
        """阻塞等待任务结果（强化容错解析）"""
        timeout = timeout or self.task_timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            task_status = self.get_task_status(task_id)
            if task_status is None:
                with LOG_LOCK:
                    logger.error(f"任务异常或被强制停止 | task_id: {task_id}")
                return None
            current_status = task_status["status"]
            if current_status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT, TaskStatus.STOPPED]:
                try:
                    remarks = task_status["remarks"] or ""
                    # 核心：兼容「成功/失败」状态，只要有执行结果就解析
                    if "执行结果: " in remarks:
                        result_str = remarks.split("执行结果: ")[-1].split(" | 业务备注: ")[0]  # 精准提取结果json
                        try:
                            raw_result = json.loads(result_str)
                        except (json.JSONDecodeError, TypeError):
                            raw_result = result_str
                        with LOG_LOCK:
                            if current_status == TaskStatus.SUCCESS:
                                # 提取业务备注部分
                                business_remarks = ""
                                if " | 业务备注: " in remarks:
                                    business_remarks = remarks.split(" | 业务备注: ")[-1]
                                elif remarks:
                                    business_remarks = remarks
                                
                                if business_remarks:
                                    logger.info(f"任务执行完成 | task_id: {task_id} | {business_remarks}")
                                else:
                                    logger.info(f"任务执行完成 | task_id: {task_id}")
                            else:
                                logger.warning(
                                    f"任务标记为{current_status}，但检测到执行结果 | task_id: {task_id} | 结果: {str(raw_result)[:500]}")
                        return raw_result
                    # 无执行结果时，返回空字典而非None，避免上层逻辑崩溃
                    with LOG_LOCK:
                        if current_status == TaskStatus.SUCCESS:
                            logger.info(f"任务执行成功，但无解析结果 | task_id: {task_id} | 执行备注: {remarks[:200] if remarks else '无'}")
                        else:
                            logger.error(
                                f"任务执行失败 | task_id: {task_id} | 状态: {current_status} | 原因: {remarks[:300]}")
                    return {}  # 替换None为{}，容错
                except Exception as e:
                    logger.error(f"解析任务结果失败 | task_id: {task_id} | 错误: {e}", exc_info=True)
                    return {}  # 替换None为{}，容错
            time.sleep(poll_interval)
        with LOG_LOCK:
            logger.error(f"任务等待超时 | task_id: {task_id} | 已等待: {timeout}秒")
        return {}  # 替换None为{}，容错

    def read_log_file_content(self, max_lines: int = None, keyword: str = None, encoding: str = "utf-8") -> str:
        """安全读取日志文件内容（加锁保证读写安全）"""
        with LOG_LOCK:
            try:
                if not os.path.exists(TOTAL_LOG_FILE):
                    return "日志文件不存在"
                with open(TOTAL_LOG_FILE, "r", encoding=encoding, errors="ignore") as f:
                    lines = f.readlines()
                if keyword:
                    lines = [line for line in lines if keyword in line]
                    if not lines:
                        return f"未找到包含关键词「{keyword}」的日志"
                if max_lines and isinstance(max_lines, int) and max_lines > 0:
                    lines = lines[-max_lines:]
                content = "".join([line.rstrip() + "\n" for line in lines if line.strip()])
                return content if content else "日志文件为空"
            except Exception as e:
                error_msg = f"读取日志文件失败：{str(e)}"
                logger.error(error_msg)
                return error_msg

    def write_log_file_content(self, content: str, encoding: str = "utf-8") -> tuple[bool, str]:
        """安全写入日志文件内容（加锁保证读写安全）"""
        with LOG_LOCK:
            try:
                with open(TOTAL_LOG_FILE, "w", encoding=encoding) as f:
                    f.write(content)
                logger.info(f"日志文件写入成功 | 文件路径: {TOTAL_LOG_FILE}")
                return True, "日志文件写入成功"
            except PermissionError:
                error_msg = f"权限不足，无法写入日志文件 | 文件路径: {TOTAL_LOG_FILE}"
                logger.error(error_msg)
                return False, error_msg
            except Exception as e:
                error_msg = f"写入日志文件失败：{str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg

    def clean_total_log_file(self) -> tuple[bool, str]:
        """清空total_log.txt日志文件（线程安全）"""
        with LOG_LOCK:
            try:
                if not os.path.exists(TOTAL_LOG_FILE):
                    return True, "日志文件不存在，无需清理"
                with open(TOTAL_LOG_FILE, "w", encoding="utf-8") as f:
                    f.truncate(0)
                logger.info(f"日志文件清空成功 | 文件路径: {TOTAL_LOG_FILE}")
                return True, "全部任务日志清理成功"
            except PermissionError:
                error_msg = f"权限不足，无法清空日志文件 | 文件路径: {TOTAL_LOG_FILE}"
                logger.error(error_msg)
                return False, error_msg
            except Exception as e:
                error_msg = f"清空日志文件失败：{str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg

    def stop_task(self, task_id: str) -> bool:
        """停止指定任务"""
        try:
            task = self.db.execute_sql(
                "SELECT status FROM task WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            if not task:
                logger.warning(f"任务不存在 | task_id: {task_id}")
                return False
            if task["status"] in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT]:
                logger.warning(f"任务已完成，无需停止 | task_id: {task_id} | 状态: {task['status']}")
                return True
            self.update_task_field(
                task_id,
                status=TaskStatus.STOPPED,
                msg="任务已退出",
                remarks=f"停止时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            logger.info(f"任务停止成功 | task_id: {task_id}")
            with EXECUTING_FLAG_LOCK:
                if task_id in TASK_EXECUTING_FLAG:
                    del TASK_EXECUTING_FLAG[task_id]
            with self._lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
            # 被动模式：清理去重集合和队列
            if self.mode == TaskManagerMode.PASSIVE:
                with self._received_task_lock:
                    self._received_task_ids.discard(task_id)
                # 清理队列中的任务（如果存在）
                try:
                    temp_queue = Queue()
                    while not self._passive_task_queue.empty():
                        tid = self._passive_task_queue.get(block=False)
                        if tid != task_id:
                            temp_queue.put(tid)
                        self._passive_task_queue.task_done()
                    # 还原队列
                    while not temp_queue.empty():
                        self._passive_task_queue.put(temp_queue.get(block=False))
                except:
                    pass
            return True
        except Exception as e:
            logger.error(f"停止任务失败 | task_id: {task_id} | 原因: {e}", exc_info=True)
            return False

    def get_all_tasks(self, format_dict: bool = True) -> List[Dict]:
        """获取所有任务"""
        try:
            tasks = self.db.execute_sql("SELECT * FROM task ORDER BY create_time DESC", fetch="fetch")
            if format_dict:
                return [dict(task) for task in tasks]
            return tasks
        except Exception as e:
            logger.error(f"获取所有任务失败：{e}")
            return []

    def get_task_count(self) -> Dict[str, int]:
        """获取各状态任务数量"""
        try:
            sql = "SELECT status, COUNT(*) as count FROM task GROUP BY status"
            result = self.db.execute_sql(sql, fetch="fetch")
            count_dict = {"pending": 0, "running": 0, "success": 0, "failed": 0, "timeout": 0, "stopped": 0}
            status_map = {
                TaskStatus.PENDING: "pending",
                TaskStatus.RUNNING: "running",
                TaskStatus.SUCCESS: "success",
                TaskStatus.FAILED: "failed",
                TaskStatus.TIMEOUT: "timeout",
                TaskStatus.STOPPED: "stopped"
            }
            for item in result:
                en_status = status_map.get(item["status"], "other")
                if en_status in count_dict:
                    count_dict[en_status] = item["count"]
            return count_dict
        except Exception as e:
            logger.error(f"获取任务数量失败：{e}")
            raise

    def get_tasks_by_status(self, status_en: str) -> List[Dict]:
        """按状态查询任务"""
        status_map = {
            "pending": TaskStatus.PENDING,
            "running": TaskStatus.RUNNING,
            "success": TaskStatus.SUCCESS,
            "failed": TaskStatus.FAILED,
            "timeout": TaskStatus.TIMEOUT,
            "stopped": TaskStatus.STOPPED
        }
        if status_en not in status_map:
            return []
        try:
            tasks = self.db.execute_sql(
                "SELECT * FROM task WHERE status = ? ORDER BY create_time DESC",
                params=[status_map[status_en]],
                fetch="fetch"
            )
            return [dict(task) for task in tasks]
        except Exception as e:
            logger.error(f"按状态查询任务失败：{e}")
            return []

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """查询单个任务状态（加锁）"""
        try:
            task = self.db.execute_sql(
                "SELECT * FROM task WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            return dict(task) if task else {"status": "unknown"}
        except Exception as e:
            logger.error(f"查询任务状态失败：{task_id} | {e}")
            return None

    def start(self):
        """启动任务管理器"""
        with LOG_LOCK:
            # 启动定时任务执行器
            try:
                from utils.scheduled_task_executor import ScheduledTaskExecutor
                self.scheduled_task_executor = ScheduledTaskExecutor(check_interval=60)
                self.scheduled_task_executor.start()
                logger.info("✅ 定时任务执行器已启动")
            except Exception as e:
                logger.error(f"❌ 定时任务执行器启动失败: {e}", exc_info=True)
            
            logger.info(
                f"日志任务管理器启动成功 | 工作模式: {self.mode.upper()} | 进程PID: {os.getpid()} "
                f"| 全局最大并发: {self.global_max_concurrent} | 任务超时: {self.task_timeout}秒 "
                f"| 功能并发配置: {self.func_concurrent_config}"
            )

    def stop(self):
        """彻底停止任务管理器"""
        with LOG_LOCK:
            logger.info(f"===== 开始执行任务管理器停止流程 | 工作模式: {self.mode.upper()} | 进程PID: {os.getpid()} =====")
        try:
            # 停止定时任务执行器
            if self.scheduled_task_executor:
                try:
                    self.scheduled_task_executor.stop()
                    logger.info("✅ 定时任务执行器已停止")
                except Exception as e:
                    logger.error(f"❌ 定时任务执行器停止失败: {e}", exc_info=True)
            
            self._stop_flag.set()
            with LOG_LOCK:
                logger.info("✅ 已设置停止标志，轮询线程将停止拾取新任务")
            running_task_ids = list(self.running_tasks.keys())
            if running_task_ids:
                with LOG_LOCK:
                    logger.info(f"📌 开始处理运行中任务 | 数量: {len(running_task_ids)}")
                for task_id in running_task_ids:
                    self.update_task_field(
                        task_id,
                        status=TaskStatus.STOPPED,
                        msg="任务管理器停止，强制终止任务",
                        remarks=f"终止时间: {datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    with self._lock:
                        task_thread = self.running_tasks.get(task_id)
                    if task_thread and task_thread.is_alive():
                        try:
                            task_thread.join(timeout=1.0)
                            with LOG_LOCK:
                                logger.info(f"✅ 任务线程已终止 | task_id: {task_id}")
                        except Exception as e:
                            with LOG_LOCK:
                                logger.warning(f"⚠️ 任务线程终止超时，强制回收 | task_id: {task_id} | 错误: {str(e)[:30]}")
                    with EXECUTING_FLAG_LOCK:
                        if task_id in TASK_EXECUTING_FLAG:
                            del TASK_EXECUTING_FLAG[task_id]
                    with self._lock:
                        if task_id in self.running_tasks:
                            del self.running_tasks[task_id]
                with LOG_LOCK:
                    logger.info(f"✅ 所有运行中任务已处理完成 | 累计终止: {len(running_task_ids)}")
            else:
                with LOG_LOCK:
                    logger.info("✅ 无运行中任务，跳过任务终止步骤")
            if self._poll_thread and self._poll_thread.is_alive():
                with LOG_LOCK:
                    logger.info("📌 等待任务拾取轮询线程退出...")
                self._poll_thread.join(timeout=10.0)
                if not self._poll_thread.is_alive():
                    with LOG_LOCK:
                        logger.info("✅ 任务拾取轮询线程已成功退出")
                else:
                    with LOG_LOCK:
                        logger.warning("⚠️ 任务拾取轮询线程超时未退出，已强制回收")
            with THREAD_TASK_LOCK:
                THREAD_TASK_MAP.clear()
            with EXECUTING_FLAG_LOCK:
                TASK_EXECUTING_FLAG.clear()
            with self._group_sem_lock:
                self._group_semaphores.clear()
            with self._received_task_lock:
                self._received_task_ids.clear()
            # 清空被动模式队列
            while not self._passive_task_queue.empty():
                try:
                    self._passive_task_queue.get(block=False)
                    self._passive_task_queue.task_done()
                except:
                    break
            with LOG_LOCK:
                logger.info("✅ 已清空全局线程映射、执行标记、分组信号量和被动任务队列")
            while self._global_semaphore._value < self.global_max_concurrent:
                self._global_semaphore.release()
            with self._group_sem_lock:
                for sem in self._group_semaphores.values():
                    while sem._value < getattr(sem, "_max_value", 1):
                        sem.release()
            with LOG_LOCK:
                logger.info("✅ 已释放所有信号量许可，并发控制已还原初始状态")
            try:
                self.db.close()
                with LOG_LOCK:
                    logger.info("✅ 数据库已安全关闭，防止文件损坏")
            except Exception as e:
                with LOG_LOCK:
                    logger.warning(f"⚠️ 数据库关闭异常（非致命）| 错误: {str(e)[:50]}")
            self.running_tasks.clear()
            with LOG_LOCK:
                logger.info(f"===== 任务管理器停止流程执行完成 | 进程PID: {os.getpid()} =====")
        except Exception as e:
            with LOG_LOCK:
                logger.error(f"❌ 任务管理器停止过程出现异常 | 错误: {e}", exc_info=True)
        finally:
            with self._lock:
                self.running_tasks.clear()
            with THREAD_TASK_LOCK:
                THREAD_TASK_MAP.clear()
            with EXECUTING_FLAG_LOCK:
                TASK_EXECUTING_FLAG.clear()

    def _cleanup_orphaned_tasks(self):
        """清理长时间处于 RUNNING 但无活跃记录的任务（防进程崩溃导致的任务卡死）"""
        timeout_seconds = config_manager.get_or_set_config("task_timeout_seconds", 3600, value_type="int")
        cutoff_time = int(time.time()) - timeout_seconds
        self.db.execute_sql(
            "UPDATE task SET status = ? WHERE status = ? AND update_time < ?",
            params=[TaskStatus.TIMEOUT, TaskStatus.RUNNING, cutoff_time],
            fetch="none"
        )

def check_task_stopped(task_log_manager, task_id):
    """检查任务是否被停止，若是则抛出异常"""
    try:
        task_status = task_log_manager.get_task_status(task_id)
        if task_status and task_status.get("status") == TaskStatus.STOPPED:
            raise RuntimeError(f"任务 {task_id} 已退出")
    except Exception as e:
        logger.error(f"检查任务状态失败 | task_id: {task_id} | 错误：{e}")
        raise


# 新增：全局获取进程内唯一TaskLogManager实例的方法（支持指定工作模式）
def get_task_log_manager(
    max_concurrent_tasks=None,
    task_timeout=3600,
    poll_interval=5,
    mode: str = TaskManagerMode.ACTIVE
) -> TaskLogManager:
    """
    获取当前进程的唯一任务管理器实例（支持指定工作模式）nb
    所有业务代码均通过此方法获取实例，禁止直接new TaskLogManager()
    :param max_concurrent_tasks: 全局最大并发数，如果为None则从配置文件读取
    :param mode: 工作模式 - TaskManagerMode.ACTIVE 主动拾取模式/TaskManagerMode.PASSIVE 被动接收模式
    """
    return TaskLogManager(max_concurrent_tasks, task_timeout, poll_interval, mode)


if __name__ == "__main__":
    # 示例1：启动主动模式任务管理器（原逻辑，FastAPI中使用）
    # active_manager = get_task_log_manager(mode=TaskManagerMode.ACTIVE)
    # active_manager.start()

    # 示例2：启动被动模式任务管理器（独立进程，供中心化分配）
    passive_manager = get_task_log_manager(max_concurrent_tasks=50, mode=TaskManagerMode.PASSIVE)
    passive_manager.start()

    # 示例：模拟中心化分配线程推送任务
    # def mock_allocate_task(manager, task_id):
    #     manager.passive_receive_task(task_id)
    #
    # # 模拟添加任务
    # def test_func(a, b):
    #     return a + b
    #
    # task_id = passive_manager.add_task(
    #     target_func=test_func,
    #     task_group="test_shop_测试功能",
    #     mall_id=1,
    #     task_name="测试任务",
    #     is_main_task=1,
    #     a=1,
    #     b=2
    # )
    # print(f"创建测试任务ID: {task_id}")
    #
    # # 模拟中心化分配
    # mock_allocate_task(passive_manager, task_id)
    #
    # # 等待结果
    # result = passive_manager.get_task_result(task_id, timeout=10)
    # print(f"任务执行结果: {result}")