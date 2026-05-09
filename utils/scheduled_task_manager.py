"""
定时任务管理器
负责管理定时任务的创建、更新、删除和执行
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger


class ScheduledTaskManager:
    """定时任务管理器"""
    
    def __init__(self, db):
        self.db = db
    
    def add_scheduled_task(
        self,
        task_id: str,
        schedule_type: str,
        schedule_time: Optional[str] = None,
        schedule_interval: Optional[int] = None,
        schedule_enabled: bool = True,
        execute_immediately: bool = True
    ) -> bool:
        """
        添加定时任务
        
        :param task_id: 任务ID
        :param schedule_type: 定时类型 'once' 或 'interval'
        :param schedule_time: 定时执行时间，格式 'HH:MM'（仅当 schedule_type='once' 时使用）
        :param schedule_interval: 执行间隔时间（分钟）（仅当 schedule_type='interval' 时使用）
        :param schedule_enabled: 是否启用定时
        :param execute_immediately: 是否立即执行
        :return: 是否添加成功
        """
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 检查任务是否存在于 task 表或 hupu_task 表中
            task_exists = self.db.execute_sql(
                "SELECT task_id FROM task WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            
            # 如果 task 表中不存在，检查 hupu_task 表
            if not task_exists:
                # 检查 hupu_post_list 表
                hupu_post_exists = self.db.execute_sql(
                    "SELECT task_id FROM hupu_post_list WHERE task_id = ?",
                    params=[task_id],
                    fetch="fetch_one"
                )
                # 检查 hupu_detail_list 表
                hupu_detail_exists = self.db.execute_sql(
                    "SELECT task_id FROM hupu_detail_list WHERE task_id = ?",
                    params=[task_id],
                    fetch="fetch_one"
                )
                # 检查 hupu_score_list 表
                hupu_score_exists = self.db.execute_sql(
                    "SELECT task_id FROM hupu_score_list WHERE task_id = ?",
                    params=[task_id],
                    fetch="fetch_one"
                )
                
                if not hupu_post_exists and not hupu_detail_exists and not hupu_score_exists:
                    logger.error(f"❌ 任务不存在 | task_id: {task_id}，无法添加定时任务")
                    return False
                
                logger.info(f"✅ 虎扑任务存在检查通过 | task_id: {task_id}")
            else:
                logger.info(f"✅ 任务存在检查通过 | task_id: {task_id}")
            
            # 检查是否已存在该任务的定时任务
            existing_task = self.db.execute_sql(
                "SELECT * FROM scheduled_tasks WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            
            if existing_task:
                logger.info(f"ℹ️ 定时任务已存在，准备更新 | task_id: {task_id}")
            else:
                logger.info(f"ℹ️ 定时任务不存在，准备插入 | task_id: {task_id}")
            
            # 计算下次执行时间
            if schedule_type == 'once' and schedule_time:
                # 定时时间执行：每日定时执行
                today = datetime.now()
                schedule_datetime = datetime.strptime(f"{today.strftime('%Y-%m-%d')} {schedule_time}", '%Y-%m-%d %H:%M')
                
                if execute_immediately:
                    # 立即执行：当前时间
                    schedule_next_run = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    # 不立即执行：到指定时间执行
                    if schedule_datetime <= today:
                        # 如果指定时间已过，设置为明天
                        schedule_datetime += timedelta(days=1)
                    schedule_next_run = schedule_datetime.strftime('%Y-%m-%d %H:%M:%S')
            elif schedule_type == 'interval' and schedule_interval:
                # 定时间隔执行：计算下次执行时间
                if execute_immediately:
                    # 立即执行：当前时间 + 间隔
                    schedule_next_run = (datetime.now() + timedelta(minutes=schedule_interval)).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    # 不立即执行：当前时间 + 间隔
                    schedule_next_run = (datetime.now() + timedelta(minutes=schedule_interval)).strftime('%Y-%m-%d %H:%M:%S')
            else:
                # 不使用定时
                schedule_next_run = None
            
            if existing_task:
                # 更新现有定时任务
                update_sql = """
                    UPDATE scheduled_tasks SET 
                    schedule_type = ?, schedule_time = ?, schedule_interval = ?, 
                    schedule_enabled = ?, schedule_next_run = ?, last_run_time = ?, run_count = ?
                    WHERE task_id = ?
                """
                logger.info(f"准备更新定时任务 | task_id: {task_id} | params: {schedule_type}, {schedule_time}, {schedule_interval}, {schedule_enabled}, {schedule_next_run}")
                self.db.execute_sql(update_sql, params=[
                    schedule_type,
                    schedule_time or '',
                    schedule_interval or 0,
                    1 if schedule_enabled else 0,
                    schedule_next_run or '',
                    '',
                    0,
                    task_id
                ], commit=True)
                logger.info(f"✅ 定时任务更新成功 | task_id: {task_id} | schedule_type: {schedule_type}")
            else:
                # 插入新的定时任务
                logger.info(f"准备插入定时任务 | task_id: {task_id} | params: {schedule_type}, {schedule_time}, {schedule_interval}, {schedule_enabled}, {schedule_next_run}")
                self.db.execute_sql("""
                    INSERT INTO scheduled_tasks (
                        task_id, schedule_type, schedule_time, schedule_interval, 
                        schedule_enabled, schedule_next_run, last_run_time, run_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, params=[
                    task_id,
                    schedule_type,
                    schedule_time or '',
                    schedule_interval or 0,
                    1 if schedule_enabled else 0,
                    schedule_next_run or '',
                    '',
                    0
                ], commit=True)
                logger.info(f"✅ 定时任务添加成功 | task_id: {task_id} | schedule_type: {schedule_type}")
            
            # 如果需要立即执行，调用重跑函数
            if execute_immediately:
                try:
                    from api.server_routes.task_routes import re_run_task_thread
                    result = re_run_task_thread(task_id)
                    if result.get("success"):
                        logger.info(f"✅ 定时任务立即执行成功 | task_id: {task_id}")
                    else:
                        logger.warning(f"⚠️ 定时任务立即执行失败 | task_id: {task_id}")
                except Exception as e:
                    logger.error(f"❌ 定时任务立即执行异常 | task_id: {task_id} | 错误: {e}")
            else:
                # 不立即执行，不修改任务状态，让任务保持原状态
                logger.info(f"ℹ️ 定时任务不立即执行，等待定时触发 | task_id: {task_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 定时任务添加失败 | task_id: {task_id} | 错误: {e}")
            return False
    
    def update_scheduled_task(
        self,
        schedule_id: int,
        schedule_type: Optional[str] = None,
        schedule_time: Optional[str] = None,
        schedule_interval: Optional[int] = None,
        schedule_enabled: Optional[bool] = None,
        execute_immediately: Optional[bool] = None
    ) -> bool:
        """
        更新定时任务配置
        
        :param schedule_id: 定时任务ID
        :param schedule_type: 定时类型
        :param schedule_time: 定时执行时间
        :param schedule_interval: 执行间隔时间（分钟）
        :param schedule_enabled: 是否启用定时
        :param execute_immediately: 是否立即执行
        :return: 是否更新成功
        """
        try:
            # 获取当前定时任务配置
            current_task = self.db.execute_sql(
                "SELECT * FROM scheduled_tasks WHERE id = ?",
                params=[schedule_id],
                fetch="fetch_one"
            )
            
            if not current_task:
                logger.error(f"❌ 定时任务不存在 | schedule_id: {schedule_id}")
                return False
            
            # 构建更新SQL
            update_fields = []
            update_values = []
            
            if schedule_type is not None:
                update_fields.append("schedule_type = ?")
                update_values.append(schedule_type)
            
            if schedule_time is not None:
                update_fields.append("schedule_time = ?")
                update_values.append(schedule_time)
            
            if schedule_interval is not None:
                update_fields.append("schedule_interval = ?")
                update_values.append(schedule_interval)
            
            if schedule_enabled is not None:
                update_fields.append("schedule_enabled = ?")
                update_values.append(1 if schedule_enabled else 0)
            
            if execute_immediately is not None:
                # 如果修改了立即执行选项，重新计算下次执行时间
                task_id = current_task['task_id']
                current_type = schedule_type or current_task['schedule_type']
                current_interval = schedule_interval or current_task['schedule_interval']
                current_time_str = schedule_time or current_task['schedule_time']
                
                if current_type == 'once' and current_time_str:
                    today = datetime.now()
                    schedule_datetime = datetime.strptime(f"{today.strftime('%Y-%m-%d')} {current_time_str}", '%Y-%m-%d %H:%M')
                    
                    if execute_immediately:
                        # 立即执行：当前时间
                        schedule_next_run = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        # 不立即执行：到指定时间执行
                        if schedule_datetime <= today:
                            schedule_datetime += timedelta(days=1)
                        schedule_next_run = schedule_datetime.strftime('%Y-%m-%d %H:%M:%S')
                    
                    update_fields.append("schedule_next_run = ?")
                    update_values.append(schedule_next_run)
                    
                elif current_type == 'interval' and current_interval:
                    if execute_immediately:
                        # 立即执行：当前时间 + 间隔
                        schedule_next_run = (datetime.now() + timedelta(minutes=current_interval)).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        # 不立即执行：保持当前下次执行时间
                        schedule_next_run = current_task['schedule_next_run']
                    
                    update_fields.append("schedule_next_run = ?")
                    update_values.append(schedule_next_run)
            
            # 添加更新时间
            update_fields.append("updated_time = ?")
            update_values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            # 执行更新
            if update_fields:
                update_sql = f"UPDATE scheduled_tasks SET {', '.join(update_fields)} WHERE id = ?"
                update_values.append(schedule_id)
                
                self.db.execute_sql(update_sql, params=update_values, commit=True)
                logger.info(f"✅ 定时任务更新成功 | schedule_id: {schedule_id}")
            else:
                logger.info(f"ℹ️ 定时任务无需更新 | schedule_id: {schedule_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 定时任务更新失败 | schedule_id: {schedule_id} | 错误: {e}")
            return False
    
    def delete_scheduled_task(self, schedule_id: int) -> bool:
        """
        删除定时任务
        
        :param schedule_id: 定时任务ID
        :return: 是否删除成功
        """
        try:
            self.db.execute_sql(
                "DELETE FROM scheduled_tasks WHERE id = ?",
                params=[schedule_id],
                commit=True
            )
            logger.info(f"✅ 定时任务删除成功 | schedule_id: {schedule_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 定时任务删除失败 | schedule_id: {schedule_id} | 错误: {e}")
            return False
    
    def disable_scheduled_task(self, task_id: str) -> bool:
        """
        禁用定时任务（通过设置 schedule_enabled = 0）
        
        :param task_id: 任务ID
        :return: 是否禁用成功
        """
        try:
            self.db.execute_sql(
                "UPDATE scheduled_tasks SET schedule_enabled = 0, updated_time = ? WHERE task_id = ?",
                params=[datetime.now().strftime('%Y-%m-%d %H:%M:%S'), task_id],
                commit=True
            )
            logger.info(f"✅ 定时任务禁用成功 | task_id: {task_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 定时任务禁用失败 | task_id: {task_id} | 错误: {e}")
            return False
    
    def get_scheduled_task_by_task_id(self, task_id: str) -> Optional[Dict]:
        """
        根据任务ID获取定时任务配置
        
        :param task_id: 任务ID
        :return: 定时任务配置字典
        """
        try:
            result = self.db.execute_sql(
                "SELECT * FROM scheduled_tasks WHERE task_id = ? ORDER BY id DESC LIMIT 1",
                params=[task_id],
                fetch="fetch_one"
            )
            if result:
                # 将datetime对象转换为字符串，避免JSON序列化错误
                result_dict = dict(result)
                for key, value in result_dict.items():
                    if isinstance(value, datetime):
                        result_dict[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                return result_dict
            return None
        except Exception as e:
            logger.error(f"❌ 获取定时任务失败 | task_id: {task_id} | 错误: {e}")
            return None
    
    def get_all_scheduled_tasks(self, enabled_only: bool = True) -> List[Dict]:
        """
        获取所有定时任务
        
        :param enabled_only: 是否只获取启用的任务
        :return: 定时任务列表
        """
        try:
            if enabled_only:
                results = self.db.execute_sql(
                    "SELECT * FROM scheduled_tasks WHERE schedule_enabled = 1 ORDER BY created_time DESC",
                    fetch="fetch"
                )
            else:
                results = self.db.execute_sql(
                    "SELECT * FROM scheduled_tasks ORDER BY created_time DESC",
                    fetch="fetch"
                )
            return results
        except Exception as e:
            logger.error(f"❌ 获取定时任务列表失败 | 错误: {e}")
            return []
    
    def get_tasks_to_execute(self) -> List[Dict]:
        """
        获取需要执行的定时任务
        
        :return: 需要执行的定时任务列表
        """
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 查询需要执行的任务
            results = self.db.execute_sql("""
                SELECT st.*, t.status as task_status
                FROM scheduled_tasks st
                LEFT JOIN task t ON st.task_id = t.task_id
                WHERE st.schedule_enabled = 1
                  AND st.schedule_next_run <= ?
                ORDER BY st.schedule_next_run ASC
            """, params=[current_time], fetch="fetch")
            
            return results
        except Exception as e:
            logger.error(f"❌ 获取待执行定时任务失败 | 错误: {e}")
            return []
    
    def update_task_run_time(self, schedule_id: int, schedule_type: str, schedule_interval: Optional[int] = None) -> bool:
        """
        更新任务执行时间和下次执行时间
        
        :param schedule_id: 定时任务ID
        :param schedule_type: 定时类型
        :param schedule_interval: 执行间隔时间（分钟）
        :return: 是否更新成功
        """
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 计算下次执行时间
            if schedule_type == 'once':
                # 每日定时执行：计算明天的同一时间
                current_task = self.db.execute_sql(
                    "SELECT schedule_time FROM scheduled_tasks WHERE id = ?",
                    params=[schedule_id],
                    fetch="fetch_one"
                )
                
                if current_task and current_task.get('schedule_time'):
                    schedule_time = current_task['schedule_time']
                    today = datetime.now()
                    schedule_datetime = datetime.strptime(f"{today.strftime('%Y-%m-%d')} {schedule_time}", '%Y-%m-%d %H:%M')
                    # 设置为明天的同一时间
                    schedule_datetime += timedelta(days=1)
                    next_run = schedule_datetime.strftime('%Y-%m-%d %H:%M:%S')
                    
                    self.db.execute_sql("""
                        UPDATE scheduled_tasks 
                        SET schedule_next_run = ?, last_run_time = ?, run_count = run_count + 1, updated_time = ?
                        WHERE id = ?
                    """, params=[next_run, current_time, current_time, schedule_id], commit=True)
                else:
                    # 如果没有schedule_time，禁用任务
                    self.db.execute_sql("""
                        UPDATE scheduled_tasks 
                        SET schedule_enabled = 0, last_run_time = ?, updated_time = ?
                        WHERE id = ?
                    """, params=[current_time, current_time, schedule_id], commit=True)
            elif schedule_type == 'interval' and schedule_interval:
                # 间隔任务，计算下次执行时间
                next_run = (datetime.now() + timedelta(minutes=schedule_interval)).strftime('%Y-%m-%d %H:%M:%S')
                self.db.execute_sql("""
                    UPDATE scheduled_tasks 
                    SET schedule_next_run = ?, last_run_time = ?, run_count = run_count + 1, updated_time = ?
                    WHERE id = ?
                """, params=[next_run, current_time, current_time, schedule_id], commit=True)
            
            logger.info(f"✅ 定时任务执行时间更新成功 | schedule_id: {schedule_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 定时任务执行时间更新失败 | schedule_id: {schedule_id} | 错误: {e}")
            return False