"""
定时任务执行器
负责定期检查并执行定时任务
"""
import time
import threading
from datetime import datetime
from typing import Optional

from loguru import logger

from config.common_config import db
from config.start_config import MAIN_TASK_MANAGER
from utils.multiThreading_log_manager import get_task_log_manager, generate_unique_task_id, TaskStatus
from utils.scheduled_task_manager import ScheduledTaskManager


class ScheduledTaskExecutor:
    """定时任务执行器"""
    
    def __init__(self, check_interval: int = 60):
        """
        初始化定时任务执行器
        
        :param check_interval: 检查间隔（秒），默认60秒
        """
        self.check_interval = check_interval
        self.schedule_manager = ScheduledTaskManager(db)
        self.running = False
        self.thread = None
        
    def start(self):
        """启动定时任务执行器"""
        if self.running:
            logger.warning("定时任务执行器已在运行中")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("定时任务执行器已启动")
    
    def _run(self):
        """定时任务执行器运行方法"""
        while self.running:
            try:
                self.check_and_execute_tasks()
            except Exception as e:
                logger.error(f"定时任务执行器异常: {e}", exc_info=True)
            
            # 使用可中断的睡眠，每秒检查一次是否需要退出
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def stop(self):
        """停止定时任务执行器"""
        if not self.running:
            logger.info("定时任务执行器未在运行，无需停止")
            return
            
        self.running = False
        logger.info("定时任务执行器已发出停止信号")
        
        # 等待线程退出
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning("定时任务执行器线程停止超时")
            else:
                logger.info("定时任务执行器线程已停止")
    
    def check_and_execute_tasks(self):
        """检查并执行需要运行的定时任务"""
        try:
            # 获取需要执行的任务
            tasks_to_execute = self.schedule_manager.get_tasks_to_execute()
            
            if not tasks_to_execute:
                return
            
            logger.info(f"发现 {len(tasks_to_execute)} 个需要执行的定时任务")
            
            for idx, scheduled_task in enumerate(tasks_to_execute, 1):
                try:
                    self.execute_scheduled_task(scheduled_task)
                except Exception as e:
                    logger.error(f"执行定时任务失败 | schedule_id: {scheduled_task['id']} | 错误: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"检查定时任务失败: {e}", exc_info=True)
    
    def execute_scheduled_task(self, scheduled_task: dict):
        """
        执行定时任务（使用re_run重跑）
        
        :param scheduled_task: 定时任务信息
        """
        task_id = scheduled_task['task_id']
        schedule_id = scheduled_task['id']
        schedule_type = scheduled_task['schedule_type']
        schedule_interval = scheduled_task['schedule_interval']
        
        logger.info(f"开始执行定时任务 | task_id: {task_id} | schedule_id: {schedule_id}")
        
        # 权限校验
        task_info = db.execute_sql(
            "SELECT task_name FROM task WHERE task_id = ?",
            params=[task_id],
            fetch="fetch_one"
        )
        
        if task_info:
            task_name = task_info.get("task_name", "")
            # 使用统一的权限管理器检查权限
            from config.permission_manager import permission_manager
            if not permission_manager.check_permission(task_name):
                logger.warning(f"定时任务执行被拒绝，权限不足 | task_id: {task_id} | task_name: {task_name}")
                # 更新定时任务的执行时间和下次执行时间（继续执行下一个定时任务）
                self.schedule_manager.update_task_run_time(
                    schedule_id=schedule_id,
                    schedule_type=schedule_type,
                    schedule_interval=schedule_interval
                )
                return
        
        # 如果任务状态是"已完成"，先改回"待处理"状态
        from utils.multiThreading_log_manager import TaskStatus
        current_task = db.execute_sql(
            "SELECT status FROM task WHERE task_id = ?",
            params=[task_id],
            fetch="fetch_one"
        )
        
        if current_task and current_task.get('status') == TaskStatus.SUCCESS:
            logger.info(f"定时任务状态为已完成，改回待处理状态 | task_id: {task_id}")
            db.execute_sql(
                "UPDATE task SET status = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                params=[TaskStatus.PENDING, task_id],
                fetch="none",
                commit=True
            )
        
        # 导入re_run_task_thread函数
        from api.server_routes.task_routes import re_run_task_thread
        
        # 使用re_run_task_thread重跑任务
        result = re_run_task_thread(task_id)
        
        if result.get("success"):
            logger.info(f"定时任务重跑成功 | task_id: {task_id} | 消息: {result.get('message')}")
            
            # 更新定时任务的执行时间和下次执行时间
            self.schedule_manager.update_task_run_time(
                schedule_id=schedule_id,
                schedule_type=schedule_type,
                schedule_interval=schedule_interval
            )
        else:
            logger.error(f"定时任务重跑失败 | task_id: {task_id} | 错误: {result.get('error_msg')}")
    
    def get_task_function(self, task_name: str):
        """
        根据任务名称获取对应的函数
        
        :param task_name: 任务名称
        :return: 任务函数
        """
        # 导入任务函数
        from temu_modules.temu_func_wrapper import (
            upload_real_pic_task_wrapper,
            modify_price_task_wrapper,
            adjust_price_manage_task_wrapper,
            expected_goods_place_task_wrapper,
            download_export_excel_wrapper,
            merge_all_months_excel_wrapper,
            record_all_need_colum_to_excel_wrapper,
            make_caiwu_excel_wrapper,
            all_make_caiwu_excel_wrapper,
            batch_join_delivery_wrapper
        )
        from spider_modules.hupu_func_wrapper import (
            hupu_post_list_wrapper,
            hupu_detail_list_wrapper,
            hupu_score_list_wrapper
        )
        
        # 任务名称到函数的映射
        task_function_map = {
            "上传实拍图": upload_real_pic_task_wrapper,
            "核价": modify_price_task_wrapper,
            "调价管理": adjust_price_manage_task_wrapper,
            "批量修改期望到货地点": expected_goods_place_task_wrapper,
            "导出所选月份账单": download_export_excel_wrapper,
            "融合所选月份账单": merge_all_months_excel_wrapper,
            "记录所需列到总表": record_all_need_colum_to_excel_wrapper,
            "计算并生成财务报表": make_caiwu_excel_wrapper,
            "自动生成财务报表": all_make_caiwu_excel_wrapper,
            "批量加入发货台": batch_join_delivery_wrapper,
            "虎扑帖子列表采集": hupu_post_list_wrapper,
            "虎扑帖子详情采集": hupu_detail_list_wrapper,
            "虎扑评分采集": hupu_score_list_wrapper,
        }
        
        return task_function_map.get(task_name)


# 全局定时任务执行器实例
scheduled_task_executor: Optional[ScheduledTaskExecutor] = None


def get_scheduled_task_executor() -> Optional[ScheduledTaskExecutor]:
    """获取全局定时任务执行器实例"""
    global scheduled_task_executor
    return scheduled_task_executor


def start_scheduled_task_executor():
    """启动全局定时任务执行器"""
    global scheduled_task_executor
    
    if scheduled_task_executor is None:
        scheduled_task_executor = ScheduledTaskExecutor(check_interval=60)
        # 直接启动线程，不通过任务管理器
        scheduled_task_executor.start()
        logger.info("全局定时任务执行器已启动")


def stop_scheduled_task_executor():
    """停止全局定时任务执行器"""
    global scheduled_task_executor
    
    if scheduled_task_executor is not None:
        scheduled_task_executor.stop()
        scheduled_task_executor = None
        logger.info("全局定时任务执行器已停止")


if __name__ == "__main__":
    # 测试定时任务执行器
    executor = ScheduledTaskExecutor(check_interval=60)
    executor.start()
