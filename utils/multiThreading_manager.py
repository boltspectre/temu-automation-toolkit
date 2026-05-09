import time
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, asdict, field
from queue import Queue, Empty
from typing import Dict, List, Optional, Any, Union

from loguru import logger

# 导入真实配置
from config.middleware_config import task_concurrent_config


# 任务状态枚举（移除STOPPED状态）
class TaskStatus:
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    SUCCESS = "success"  # 执行成功
    FAILED = "failed"  # 执行失败
    TIMEOUT = "timeout"  # 执行超时


@dataclass
class TaskInfo:
    """任务信息数据类，移除停止相关字段"""
    task_id: str
    func_name: str
    args: tuple
    kwargs: dict
    task_group: str  # 分组标识，格式 "店铺名_功能名" 如 "A_核价"
    status: str = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    create_time: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    thread_name: Optional[str] = None
    exec_thread_id: Optional[int] = None  # 存储任务执行线程ID


class MainTaskManager:
    """通用多线程任务管理器（精简版：移除所有停止相关功能）"""

    def __init__(self, max_concurrent_tasks=2000, task_timeout=3600):
        """
        :param max_concurrent_tasks: 全局最大并发数（兜底）
        :param task_timeout: 单个任务超时时间（秒）
        """
        # 全局并发限制
        self.global_max_concurrent = max_concurrent_tasks
        self._global_semaphore = threading.Semaphore(max_concurrent_tasks)

        # 功能并发配置
        self.func_concurrent_config = task_concurrent_config

        # 分组信号量字典（懒加载）
        self._group_semaphores: Dict[str, threading.Semaphore] = {}
        self._group_sem_lock = threading.Lock()

        # 核心属性
        self.task_timeout = task_timeout
        self.task_queue = Queue()
        self.running_futures = set()
        self.processed_task_ids = set()
        self._stop_flag = threading.Event()  # 仅用于停止管理器，非任务停止
        self._lock = threading.Lock()
        self.future_map = {}
        self.task_info_map: Dict[str, TaskInfo] = {}

    def _parse_group_name(self, group_name: str) -> tuple:
        """解析分组名，返回 (店铺名, 功能名)"""
        parts = group_name.split("_", 1)
        if len(parts) != 2:
            return "全局", "全局任务"
        return parts[0], parts[1]

    def _get_group_semaphore(self, group_name: str) -> threading.Semaphore:
        """获取分组信号量（核心并发控制）"""
        with self._group_sem_lock:
            if group_name not in self._group_semaphores:
                shop_name, func_name = self._parse_group_name(group_name)
                max_num = self.func_concurrent_config.get(func_name, self.func_concurrent_config["default"])
                self._group_semaphores[group_name] = threading.Semaphore(max_num)
                logger.info(
                    f"初始化分组信号量 | 分组: {group_name} "
                    f"| 店铺: {shop_name} | 功能: {func_name} | 最大并发: {max_num}"
                )
            return self._group_semaphores[group_name]

    def update_func_config(self, func_name: str, max_concurrent: int):
        """动态更新功能并发配置"""
        with self._group_sem_lock:
            old_max = self.func_concurrent_config.get(func_name, self.func_concurrent_config["default"])
            self.func_concurrent_config[func_name] = max_concurrent

            # 仅扩容，不缩容
            for group_name in list(self._group_semaphores.keys()):
                _, group_func = self._parse_group_name(group_name)
                if group_func == func_name and max_concurrent > old_max:
                    sem = self._group_semaphores[group_name]
                    additional = max_concurrent - old_max
                    for _ in range(additional):
                        sem.release()

        logger.info(f"更新功能并发配置 | 功能: {func_name} | 新最大并发: {max_concurrent}")

    def add_task(self, task_id, target_func, *args, task_group: str, allow_duplicate=True, **kwargs):
        """新增任务（移除停止相关逻辑）"""
        with self._lock:
            if self._stop_flag.is_set():
                logger.warning(f"任务管理器已停止，拒绝添加任务: {task_id}")
                return False
            if not allow_duplicate and task_id in self.processed_task_ids:
                logger.warning(f"任务已处理过，跳过重复提交: {task_id}")
                return False

            # 初始化任务信息
            self.task_info_map[task_id] = TaskInfo(
                task_id=task_id,
                func_name=target_func.__name__,
                args=args,
                kwargs=kwargs,
                task_group=task_group
            )

            # 加入任务队列
            task_tuple = (task_id, target_func, args, kwargs, task_group)
            self.task_queue.put(task_tuple)
            self.processed_task_ids.add(task_id)

            logger.info(
                f"已添加任务 | 任务ID: {task_id} | 分组: {task_group} | 函数: {target_func.__name__}"
            )
        return True

    def get_task_result(self, task_id, timeout=None, poll_interval=0.5):
        """轮询获取任务执行结果"""
        timeout = timeout or self.task_timeout
        start_time = time.time()

        while time.time() - start_time < timeout:
            with self._lock:
                if task_id not in self.future_map:
                    time.sleep(poll_interval)
                    continue

                obj = self.future_map[task_id]
                if isinstance(obj, Future):
                    if obj.done():
                        try:
                            result = obj.result()
                            self.future_map[task_id] = result
                            return result
                        except Exception as e:
                            result = {"code": -1, "msg": str(e)}
                            self.future_map[task_id] = result
                            return result
                    time.sleep(poll_interval)
                else:
                    return obj

        return {"code": -2, "msg": f"任务等待超时（{timeout}秒）"}

    def batch_add_tasks(self, task_list, allow_duplicate=False):
        """批量添加任务"""
        added_count = 0
        for task in task_list:
            task_id, target_func, args, kwargs, task_group = task
            if self.add_task(
                    task_id, target_func, *args,
                    task_group=task_group,
                    allow_duplicate=allow_duplicate, **kwargs
            ):
                added_count += 1
        logger.info(f"批量添加任务完成 | 总提交数: {len(task_list)} | 成功添加数: {added_count}")
        return added_count

    def _process_single_task(self, task_tuple):
        """处理单个任务（移除所有停止信号相关逻辑）"""
        task_id, target_func, args, kwargs, task_group = task_tuple
        task_info = self.task_info_map.get(task_id)
        if not task_info:
            logger.error(f"任务信息不存在，跳过处理: {task_id}")
            self.task_queue.task_done()
            return None

        # 获取并发信号量
        group_sem = self._get_group_semaphore(task_group)
        try:
            self._global_semaphore.acquire()
            group_sem.acquire()

            # 更新任务状态为运行中
            with self._lock:
                task_info.status = TaskStatus.RUNNING
                task_info.start_time = time.time()
                task_info.thread_name = threading.current_thread().name

            # 包装任务函数：仅记录线程ID，无停止信号
            def wrapped_task():
                task_info.exec_thread_id = threading.current_thread().ident
                return target_func(*args, **kwargs)

            # 执行任务
            with ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix=f'temp_task_{task_id}_'
            ) as temp_executor:
                future = temp_executor.submit(wrapped_task)
                future.task_id = task_id
                future.func_name = target_func.__name__
                future.task_group = task_group

                with self._lock:
                    self.running_futures.add(future)
                    self.future_map[task_id] = future

                future.add_done_callback(self._task_done_callback)

                # 打印并发日志
                shop_name, func_name = self._parse_group_name(task_group)
                global_used = self.global_max_concurrent - self._global_semaphore._value
                group_max = self.func_concurrent_config.get(func_name, self.func_concurrent_config["default"])
                group_used = group_max - group_sem._value
                logger.info(
                    f"任务已提交 | 任务ID: {task_id} | 店铺: {shop_name} | 功能: {func_name} "
                    f"| 全局并发: {global_used}/{self.global_max_concurrent} "
                    f"| 功能并发: {group_used}/{group_max}"
                )

                # 仅检测超时，无停止信号检测
                result = None
                while not future.done():
                    if time.time() - task_info.start_time > self.task_timeout:
                        future.cancel()
                        raise TimeoutError(f"任务{task_id}执行超时（{self.task_timeout}秒）")
                    time.sleep(0.1)

                # 获取任务结果
                result = future.result()

                # 更新成功状态
                with self._lock:
                    task_info.status = TaskStatus.SUCCESS
                    task_info.result = result
                    task_info.end_time = time.time()
                    self.future_map[task_id] = task_info.result
                return result

        except TimeoutError as e:
            # 超时处理
            with self._lock:
                task_info.status = TaskStatus.TIMEOUT
                task_info.error = str(e)
                task_info.end_time = time.time()
                self.future_map[task_id] = {"code": -1, "msg": str(e)}
            logger.error(f"任务执行超时 | 任务ID: {task_id} | 分组: {task_group} | 超时时间: {self.task_timeout}秒")
        except Exception as e:
            # 失败处理
            error_msg = str(e)
            with self._lock:
                task_info.status = TaskStatus.FAILED
                task_info.error = error_msg
                task_info.end_time = time.time()
                self.future_map[task_id] = {"code": -1, "msg": error_msg}

            shop_name, func_name = self._parse_group_name(task_group)
            logger.error(
                f"任务执行失败 | 任务ID: {task_id} | 店铺: {shop_name} | 功能: {func_name} | 异常: {e}",
                exc_info=True
            )
        finally:
            # 释放信号量
            try:
                group_sem.release()
                self._global_semaphore.release()
            except:
                pass
            self.task_queue.task_done()

    def _process_tasks(self):
        """任务处理循环"""
        # logger.info(
        #     f"通用任务管理器已启动 | 全局最大并发: {self.global_max_concurrent} "
        #     f"| 功能并发配置: {self.func_concurrent_config}"
        # )
        while not self._stop_flag.is_set():
            try:
                task_tuple = self.task_queue.get(timeout=1)
            except Empty:
                continue

            # 启动线程处理任务
            task_thread = threading.Thread(
                target=self._process_single_task,
                args=(task_tuple,),
                name=f'task_processor_{task_tuple[0]}',
                daemon=True
            )
            task_thread.start()

        self._wait_all_tasks_done()

    def _task_done_callback(self, future: Future):
        """任务完成回调（移除停止相关逻辑）"""
        task_id = getattr(future, 'task_id', '未知标识')
        task_group = getattr(future, 'task_group', '未知分组')
        func_name = getattr(future, 'func_name', '未知函数')

        try:
            result = future.result(timeout=self.task_timeout)
            shop_name, func_name = self._parse_group_name(task_group)
            group_sem = self._get_group_semaphore(task_group)
            group_remain = group_sem._value
            logger.success(
                f"任务执行完成 | 任务ID: {task_id} | 店铺: {shop_name} | 功能: {func_name} "
                f"| 剩余并发: {group_remain} | 结果: {result}"
            )
        except TimeoutError as e:
            if self.task_info_map.get(task_id):
                with self._lock:
                    self.task_info_map[task_id].status = TaskStatus.TIMEOUT
                    self.task_info_map[task_id].error = str(e)
                    self.task_info_map[task_id].end_time = time.time()
            logger.error(f"任务超时 | 任务ID: {task_id} | 异常: {e}")
        except Exception as e:
            if self.task_info_map.get(task_id):
                with self._lock:
                    self.task_info_map[task_id].status = TaskStatus.FAILED
                    self.task_info_map[task_id].error = str(e)
                    self.task_info_map[task_id].end_time = time.time()
            shop_name, func_name = self._parse_group_name(task_group)
            logger.error(
                f"任务执行异常 | 任务ID: {task_id} | 店铺: {shop_name} | 功能: {func_name} | 异常: {e}",
                exc_info=True
            )
        finally:
            with self._lock:
                self.running_futures.discard(future)

    def _wait_all_tasks_done(self):
        """等待所有剩余任务完成"""
        with self._lock:
            if not self.running_futures:
                return
            remaining_count = len(self.running_futures)
        logger.info(f"等待剩余 {remaining_count} 个任务完成...")

        with self._lock:
            running_futures = list(self.running_futures)
        for future in running_futures:
            task_id = getattr(future, 'task_id', '未知标识')
            task_group = getattr(future, 'task_group', '未知分组')
            func_name = getattr(future, 'func_name', '未知函数')
            task_info = self.task_info_map.get(task_id)

            try:
                future.result(timeout=self.task_timeout)
            except TimeoutError as e:
                if task_info:
                    with self._lock:
                        task_info.status = TaskStatus.TIMEOUT
                        task_info.error = str(e)
                        task_info.end_time = time.time()
            except Exception as e:
                if task_info:
                    with self._lock:
                        task_info.status = TaskStatus.FAILED
                        task_info.error = str(e)
                        task_info.end_time = time.time()
            finally:
                with self._lock:
                    self.running_futures.discard(future)

    # ========== 任务查询相关方法（保留，无停止逻辑） ==========
    def _filter_task_dict(self, task_dict: Dict) -> Dict:
        """过滤不可序列化字段（无停止信号字段）"""
        return task_dict

    def get_tasks_by_group(self, group_name: str, format_dict: bool = True) -> Union[List[TaskInfo], List[Dict]]:
        with self._lock:
            task_list = [t for t in self.task_info_map.values() if t.task_group == group_name]
        task_list.sort(key=lambda x: x.create_time)

        if format_dict:
            return [self._filter_task_dict(asdict(task)) for task in task_list]
        return task_list

    def get_all_tasks(self, format_dict: bool = True) -> Union[List[TaskInfo], List[Dict]]:
        with self._lock:
            task_list = list(self.task_info_map.values())
        task_list.sort(key=lambda x: x.create_time)

        if format_dict:
            return [self._filter_task_dict(asdict(task)) for task in task_list]
        return task_list

    def get_task_status(self, task_id: str, format_dict: bool = True) -> Union[Optional[TaskInfo], Optional[Dict]]:
        with self._lock:
            task_info = self.task_info_map.get(task_id)

        if task_info and format_dict:
            return self._filter_task_dict(asdict(task_info))
        return task_info

    def get_tasks_by_status(self, status: str, format_dict: bool = True) -> Union[List[TaskInfo], List[Dict]]:
        with self._lock:
            task_list = [t for t in self.task_info_map.values() if t.status == status]
        task_list.sort(key=lambda x: x.create_time)

        if format_dict:
            return [self._filter_task_dict(asdict(task)) for task in task_list]
        return task_list

    # ========== 管理器启停 ==========
    def start(self):
        """启动任务管理器"""
        self.manager_thread = threading.Thread(target=self._process_tasks, daemon=True)
        self.manager_thread.start()
        logger.info(
            f"通用任务管理器已启动 | 全局最大并发: {self.global_max_concurrent} "
            f"| 任务超时: {self.task_timeout}秒 | 功能并发配置: {self.func_concurrent_config}"
        )

    def stop(self):
        """彻底停止通用任务管理器（清理所有资源+确保进程可退出）"""
        logger.info("===== 开始执行通用任务管理器停止流程 =====")
        try:
            # 步骤1：设置停止标志，拒绝接收新任务（立即生效）
            self._stop_flag.set()
            logger.info("✅ 已设置停止标志，将不再接收新任务")

            # 步骤2：等待任务队列中待拾取的任务执行完成（原有逻辑保留）
            logger.info("📌 等待队列中待拾取任务执行完成...")
            self.task_queue.join()
            logger.info("✅ 队列中所有待拾取任务已处理完成")

            # 步骤3：强制清理所有运行中任务的临时线程池+等待任务结束
            with self._lock:
                # 复制当前运行中的Future，避免遍历中修改集合
                running_futures = list(self.running_futures)
            if running_futures:
                logger.info(f"📌 开始处理运行中任务 | 剩余任务数: {len(running_futures)}")
                for future in running_futures:
                    task_id = getattr(future, 'task_id', '未知任务ID')
                    task_info = self.task_info_map.get(task_id)
                    try:
                        # 等待任务执行完成（使用管理器超时时间，避免无限等待）
                        future.result(timeout=self.task_timeout)
                        logger.info(f"✅ 任务正常完成 | task_id: {task_id}")
                    except TimeoutError as e:
                        # 任务超时：标记状态并记录错误
                        error_msg = f"任务执行超时，强制终止 | 超时时间: {self.task_timeout}秒"
                        logger.warning(f"⚠️ {error_msg} | task_id: {task_id}")
                        if task_info:
                            with self._lock:
                                task_info.status = TaskStatus.TIMEOUT
                                task_info.error = error_msg
                                task_info.end_time = time.time()
                                self.future_map[task_id] = {"code": -2, "msg": error_msg}
                    except Exception as e:
                        # 任务异常：标记状态并记录错误
                        error_msg = f"任务执行异常：{str(e)[:50]}"
                        logger.error(f"⚠️ {error_msg} | task_id: {task_id}", exc_info=True)
                        if task_info:
                            with self._lock:
                                task_info.status = TaskStatus.FAILED
                                task_info.error = error_msg
                                task_info.end_time = time.time()
                                self.future_map[task_id] = {"code": -1, "msg": error_msg}
                    finally:
                        # 从运行中集合移除，确保资源释放
                        with self._lock:
                            self.running_futures.discard(future)
                logger.info(f"✅ 所有运行中任务已处理完成 | 累计处理: {len(running_futures)}")
            else:
                logger.info("✅ 无运行中任务，跳过任务处理步骤")

            # 步骤4：等待管理器线程彻底退出（延长超时时间，确保退出）
            if hasattr(self, 'manager_thread') and self.manager_thread.is_alive():
                logger.info("📌 等待任务管理器主线程退出...")
                # 延长超时到10秒，确保管理器线程完成剩余清理
                self.manager_thread.join(timeout=10.0)
                if self.manager_thread.is_alive():
                    logger.warning("⚠️ 任务管理器主线程超时未退出，已强制回收")
                else:
                    logger.info("✅ 任务管理器主线程已成功退出")

            # 步骤5：清空所有全局状态缓存，防止资源泄漏
            with self._lock:
                self.task_info_map.clear()
                self.future_map.clear()
                self.running_futures.clear()
                self.processed_task_ids.clear()
                self._group_semaphores.clear()
            logger.info("✅ 已清空所有全局状态缓存（任务信息/结果/信号量）")

            # 步骤6：释放所有信号量许可，还原初始状态
            # 释放全局信号量
            while self._global_semaphore._value < self.global_max_concurrent:
                self._global_semaphore.release()
            logger.info("✅ 已释放所有并发信号量许可，并发控制还原初始状态")

            logger.info("===== 通用任务管理器停止流程执行完成（无资源残留） =====")
        except Exception as e:
            logger.error(f"❌ 任务管理器停止过程出现异常 | 错误: {e}", exc_info=True)


    def stop0(self):
        """停止任务管理器（仅停止接收新任务，等待已有任务完成）"""
        logger.info("正在停止通用任务管理器...")
        self._stop_flag.set()
        self.task_queue.join()
        self.manager_thread.join(timeout=5)
        logger.info("通用任务管理器停止成功")


# ========== 简化后的使用示例 ==========
def demo_task(shop_id: int, goods_id: int):
    """示例任务函数"""
    logger.info(f"开始处理任务 | 店铺ID: {shop_id} | 商品ID: {goods_id}")
    time.sleep(2)
    logger.info(f"完成处理任务 | 店铺ID: {shop_id} | 商品ID: {goods_id}")
    return {"code": 0, "msg": f"处理完成：店铺{shop_id}-商品{goods_id}"}


if __name__ == "__main__":
    # 初始化管理器
    task_manager = MainTaskManager(max_concurrent_tasks=100, task_timeout=30)
    task_manager.start()

    # 添加单个任务
    task_manager.add_task(
        task_id="task_001",
        target_func=demo_task,
        task_group="A_核价",
        shop_id=1001,
        goods_id=20001
    )

    # 批量添加任务
    task_list = [
        ("task_002", demo_task, (), {"shop_id": 1001, "goods_id": 20002}, "A_核价"),
        ("task_003", demo_task, (), {"shop_id": 1002, "goods_id": 20003}, "B_订单同步"),
    ]
    task_manager.batch_add_tasks(task_list)

    # 获取任务结果
    time.sleep(3)
    print(task_manager.get_task_result("task_001"))

    # 停止管理器（可选）
    # task_manager.stop()
