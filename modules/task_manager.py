import os
import time
import multiprocessing
from multiprocessing import Process, Manager, RLock, Queue  # 新增Queue用于进程间通信
import threading
from typing import List, Dict, Optional, Any

# 直接导入你代码的所有组件（无需修改，保持和你项目一致）
from loguru import logger

from config.common_config import db
from utils.multiThreading_log_manager import get_task_log_manager, LOG_LOCK, TaskStatus, TaskManagerMode, TaskLogManager

# ===================== 仅配置，无新函数 =====================
PROCESS_NUM = 2  # 启动的进程数
THREAD_PER_PROC = 500  # 每个进程的最大线程数（对应你代码的max_concurrent_tasks）
DB_POLL_INTERVAL = 3  # 主进程轮询数据库间隔（秒）
SINGLE_GET_TASK_LIMIT = 10  # 单次获取待处理任务数（复用你代码的limit逻辑）
PROCESS_HEARTBEAT_TIMEOUT = 10  # 进程心跳超时时间（秒）

# ===================== 子进程：新增队列接口，内部调用_tlm（核心修复）=====================
class SubProc(Process):
    """子进程：仅初始化+启动+保活你原有被动模式的TaskLogManager，新增队列接收任务"""
    def __init__(self, proc_id: int, shared_status: Dict, proc_lock: RLock, task_queue: Queue):
        super().__init__(daemon=True, name=f"task_proc_{proc_id}")
        self.proc_id = proc_id
        self.shared_status = shared_status  # 多进程共享状态（主进程用于分发判断）
        self.proc_lock = proc_lock          # 多进程共享锁
        self.task_queue = task_queue        # 进程间通信队列，接收主进程的任务
        self._tlm: Optional[TaskLogManager] = None  # 你原有任务管理器实例
        self._stop = multiprocessing.Event()
        self.process_id = None  # 提前定义进程ID属性

    def run(self):
        """子进程主逻辑：仅调用你代码的方法，新增队列消费线程"""
        try:
            # 1. 调用你代码的get_task_log_manager，创建被动模式实例
            self._tlm = get_task_log_manager(
                max_concurrent_tasks=THREAD_PER_PROC,
                poll_interval=1,  # 被动模式短轮询，快速响应分发
                mode=TaskManagerMode.PASSIVE  # 严格使用被动模式
            )
            # 2. 调用你代码的start方法启动
            self._tlm.start()
            self.process_id = os.getpid()  # 赋值进程ID

            # 初始化共享状态
            self._update_status(status="running", task_running=0)
            with LOG_LOCK:
                logger.info(f"子进程{self.proc_id}启动成功 | PID:{self.process_id} | 被动模式 | 最大线程{THREAD_PER_PROC}")

            # 启动2个核心线程：心跳线程 + 队列消费线程（内部调用_tlm，无跨进程访问）
            threading.Thread(target=self._heartbeat, daemon=True).start()
            threading.Thread(target=self._consume_task, daemon=True).start()  # 新增：消费主进程的任务

            # 保活：仅等待停止信号，不做任何其他操作
            while not self._stop.is_set():
                time.sleep(1)

        except Exception as e:
            self._update_status(status="error", err=str(e)[:50])
            with LOG_LOCK:
                logger.error(f"子进程{self.proc_id}异常 | 错误:{e}", exc_info=True)
        finally:
            # 3. 调用你代码的stop方法优雅停止
            if self._tlm:
                self._tlm.stop()
            self._update_status(status="stopped")
            with LOG_LOCK:
                logger.info(f"子进程{self.proc_id}已停止 | PID:{self.process_id if self.process_id else '未知'}")

    def _update_status(self, **kwargs):
        """更新共享状态（主进程可见）- 保持原有修复：属性名统一为process_id"""
        with self.proc_lock:
            self.shared_status[self.proc_id] = {
                "pid": self.process_id,
                "status": "init",
                "task_running": 0,
                "last_beat": time.time(),
                "err": "",
                **kwargs
            }

    def _heartbeat(self):
        """心跳：仅调用你代码的get_task_count获取运行中任务数，作为负载指标"""
        while not self._stop.is_set():
            try:
                if self._tlm:
                    task_count = self._tlm.get_task_count()
                    self._update_status(
                        status="running",
                        task_running=task_count["running"],
                        last_beat=time.time()
                    )
                time.sleep(2)
            except Exception as e:
                with LOG_LOCK:
                    logger.warning(f"子进程{self.proc_id}心跳异常 | 错误:{e}")
                time.sleep(1)

    def _consume_task(self):
        """新增：队列消费线程，子进程内部调用_tlm.passive_receive_task（无跨进程访问）"""
        with LOG_LOCK:
            logger.info(f"子进程{self.proc_id}任务消费线程启动，开始监听任务队列")
        while not self._stop.is_set():
            try:
                # 从队列获取任务，超时1秒避免阻塞
                task_id = self.task_queue.get(timeout=1)
                if not task_id or self._stop.is_set():
                    continue
                # 子进程内部调用_tlm，完全无跨进程访问，不会出现NoneType
                if self._tlm:
                    success = self._tlm.passive_receive_task(task_id)
                    if success:
                        with LOG_LOCK:
                            logger.debug(f"子进程{self.proc_id}({self.process_id}) 成功接收任务 | task_id:{task_id}")
                    else:
                        with LOG_LOCK:
                            logger.warning(f"子进程{self.proc_id} 接收任务失败 | task_id:{task_id}，状态保持待处理")
                else:
                    with LOG_LOCK:
                        logger.warning(f"子进程{self.proc_id} _tlm未初始化，跳过任务 | task_id:{task_id}")
            except multiprocessing.queues.Empty:
                # 队列空是正常情况，无需日志
                continue
            except Exception as e:
                with LOG_LOCK:
                    logger.error(f"子进程{self.proc_id} 消费任务异常 | 错误:{str(e)[:50]}", exc_info=True)
                time.sleep(0.5)

    def stop_proc(self):
        """停止子进程"""
        self._stop.set()
        # 向队列放入空值，唤醒消费线程，避免阻塞
        try:
            self.task_queue.put(None, block=False)
        except:
            pass
        if self.is_alive():
            self.terminate()
            self.join(5)

# ===================== 主进程分配器：向队列放任务，不再直接访问_tlm（核心修复）=====================
class Distributor:
    """任务分配器：仅做「调用你代码获取任务」+「向子进程队列放任务」，完全移除跨进程_tlm访问"""
    def __init__(self):
        self.proc_num = PROCESS_NUM
        self.manager = Manager()
        self.shared_status = self.manager.dict()  # 子进程状态
        self.proc_lock = self.manager.RLock()     # 多进程锁
        self.procs: List[SubProc] = []            # 子进程池
        self.task_queues: Dict[int, Queue] = {}   # 子进程队列映射 {proc_id: 队列实例}
        self._stop = threading.Event()
        self.is_running = False

        # 启动前清理：调用你代码的db方法，重置可能的异常状态任务
        try:
            db.execute_sql(
                "UPDATE task SET status = ? WHERE status NOT IN (?, ?, ?, ?, ?)",
                params=[TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT, TaskStatus.STOPPED],
                fetch="none"
            )
            with LOG_LOCK:
                logger.info("分配器初始化完成 | 进程数{} | 单进程线程{}".format(PROCESS_NUM, THREAD_PER_PROC))
        except Exception as e:
            with LOG_LOCK:
                logger.error("初始化清理异常 | 错误:{}".format(e))

    def _start_procs(self):
        """启动所有子进程：为每个子进程创建独立队列"""
        for i in range(1, self.proc_num + 1):
            # 为每个子进程创建独立的进程间通信队列
            task_queue = Queue(maxsize=100)  # 队列最大容量100，避免主进程阻塞
            self.task_queues[i] = task_queue
            # 传入队列，创建子进程
            proc = SubProc(proc_id=i, shared_status=self.shared_status, proc_lock=self.proc_lock, task_queue=task_queue)
            proc.start()
            self.procs.append(proc)
        time.sleep(3)  # 延长等待时间，确保子进程完全初始化
        with LOG_LOCK:
            logger.success("所有子进程启动完成 | 总数:{} | 各子进程均已创建独立任务队列".format(self.proc_num))

    def _get_least_load_proc(self) -> Optional[int]:
        """优化：仅返回负载最低的子进程ID，不返回进程实例，避免误访问属性"""
        with self.proc_lock:
            valid_procs = []
            for proc in self.procs:
                if not proc.is_alive():
                    continue
                status = self.shared_status.get(proc.proc_id, {})
                if not status or status.get("status") != "running" or time.time() - status.get("last_beat", 0) > PROCESS_HEARTBEAT_TIMEOUT or not status.get("pid"):
                    continue
                valid_procs.append((proc.proc_id, status.get("task_running", 999)))

            if not valid_procs:
                return None
            # 按运行中任务数升序，返回负载最低的子进程ID
            valid_procs.sort(key=lambda x: x[1])
            return valid_procs[0][0]

    def _distribute_loop(self):
        """分发主循环：获取任务后向队列放任务，完全移除跨进程_tlm访问"""
        with LOG_LOCK:
            logger.info("任务分发循环启动 | 轮询间隔{}秒 | 单次取任务{}个 | 分发方式：进程间队列".format(DB_POLL_INTERVAL, SINGLE_GET_TASK_LIMIT))

        while not self._stop.is_set():
            try:
                # 1. 调用你代码的「原有逻辑」获取待处理任务（完全复用，无任何修改）
                pending_tasks = []
                with self._tlm_dummy._task_poll_lock:
                    pending_tasks = db.execute_sql(
                        """SELECT task_id FROM task WHERE status = ? LIMIT ?""",
                        params=[TaskStatus.PENDING, SINGLE_GET_TASK_LIMIT],
                        fetch="fetch"
                    ) or []
                seen = set()
                task_ids = []
                for t in pending_tasks:
                    tid = t["task_id"]
                    if tid not in seen:
                        seen.add(tid)
                        task_ids.append(tid)

                if not task_ids:
                    time.sleep(DB_POLL_INTERVAL)
                    continue

                # 2. 逐个分发任务：向负载最低的子进程队列放任务
                for task_id in task_ids:
                    target_proc_id = self._get_least_load_proc()
                    if not target_proc_id or target_proc_id not in self.task_queues:
                        with LOG_LOCK:
                            logger.warning("无可用子进程队列，跳过任务 | task_id:{}".format(task_id))
                            continue

                    # 核心修改：向队列放任务，不再调用target_proc._tlm.passive_receive_task
                    try:
                        task_queue = self.task_queues[target_proc_id]
                        # 非阻塞放任务，避免队列满导致主进程阻塞
                        task_queue.put(task_id, block=False)
                        with LOG_LOCK:
                            logger.debug("任务分发成功 | task_id:{} → 子进程{}".format(task_id, target_proc_id))
                    except multiprocessing.queues.Full:
                        with LOG_LOCK:
                            logger.warning("子进程{}队列已满，跳过任务 | task_id:{}".format(target_proc_id, task_id))
                    except Exception as e:
                        with LOG_LOCK:
                            logger.warning("任务分发失败 | task_id:{} → 子进程{} | 错误:{}".format(task_id, target_proc_id, str(e)[:30]))

            except Exception as e:
                with LOG_LOCK:
                    logger.error("分发循环异常 | 错误:{}".format(e), exc_info=True)
                time.sleep(1)

    def start(self):
        """启动分配器：启动子进程 + 启动分发循环"""
        if self.is_running:
            with LOG_LOCK:
                logger.warning("分配器已启动，无需重复操作")
                return

        # 创建临时dummy实例，用于复用你代码的锁和基础方法（无实际运行）
        self._tlm_dummy = get_task_log_manager(mode=TaskManagerMode.ACTIVE)
        # 启动所有子进程
        self._start_procs()
        # 启动分发线程
        threading.Thread(target=self._distribute_loop, daemon=True).start()
        self.is_running = True
        with LOG_LOCK:
            logger.success("任务分配器启动成功 | 主进程PID:{} | 采用进程间队列分发任务（无跨进程属性访问）".format(os.getpid()))

    def stop(self):
        """停止分配器：停止所有子进程，清理队列"""
        if not self.is_running:
            with LOG_LOCK:
                logger.warning("分配器未启动，无需停止")
                return

        self._stop.set()
        self.is_running = False
        with LOG_LOCK:
            logger.info("开始停止分配器，关闭所有子进程和任务队列...")

        # 停止所有子进程
        for proc in self.procs:
            proc.stop_proc()
        self.procs.clear()

        # 清理队列
        for q in self.task_queues.values():
            try:
                while not q.empty():
                    q.get(block=False)
            except:
                pass
        self.task_queues.clear()

        # 清理资源
        self.manager.shutdown()
        with LOG_LOCK:
            logger.success("分配器已完全停止 | 所有子进程和队列已清理")

# ===================== 启动入口：保持原有，无修改 =====================
if __name__ == "__main__":
    # 强制开启多进程启动方式（Windows/Linux通用）
    multiprocessing.set_start_method('spawn', force=True)
    # 初始化并启动分配器
    distributor = Distributor()
    distributor.start()

    # 主进程保活（按Ctrl+C停止）
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        distributor.stop()
        with LOG_LOCK:
            logger.info("接收到停止信号，分配器已退出")
