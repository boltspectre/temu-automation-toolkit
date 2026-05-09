"""
日志自动清理器
定期检查任务日志，当日志超过阈值时自动清理
"""
import time
import threading
from typing import Optional

from loguru import logger

from config.common_config import config_manager, db


class LogCleaner:
    """日志自动清理器"""
    
    def __init__(self):
        """初始化日志清理器"""
        self.auto_clean_enabled = False
        self.char_threshold = 100000
        self.keep_ratio = 0.1
        self.load_config()
    
    def load_config(self):
        """加载配置"""
        try:
            auto_clean_enabled = config_manager.get_or_set_config("auto_clean_log_enabled", "否")
            self.auto_clean_enabled = auto_clean_enabled == "是"
            
            char_threshold = config_manager.get_or_set_config("log_char_threshold", "100000")
            self.char_threshold = int(char_threshold)
            
            keep_ratio = config_manager.get_or_set_config("log_keep_ratio", "0.1")
            self.keep_ratio = float(keep_ratio)
            
            logger.info(f"日志清理器配置加载 | 启用: {self.auto_clean_enabled} | 阈值: {self.char_threshold} | 保留比例: {self.keep_ratio}")
        except Exception as e:
            logger.error(f"加载日志清理器配置失败: {e}")
    
    def clean_log(self, log_content: str) -> str:
        """
        清理日志内容
        
        :param log_content: 原始日志内容
        :return: 清理后的日志内容
        """
        if not log_content:
            return log_content
        
        log_length = len(log_content)
        
        # 如果日志长度未超过阈值，不清理
        if log_length <= self.char_threshold:
            return log_content
        
        # 计算保留的字符数
        keep_length = int(log_length * self.keep_ratio)
        
        # 确保至少保留一定长度的日志
        min_keep_length = 1000
        if keep_length < min_keep_length:
            keep_length = min_keep_length
        
        # 清理日志：保留最后 keep_length 个字符
        cleaned_log = log_content[-keep_length:]
        
        # 添加清理标记
        cleaned_log = f"\n[日志自动清理] 原日志长度: {log_length} 字符，已清理为: {len(cleaned_log)} 字符\n{cleaned_log}"
        
        return cleaned_log
    
    def clean_task_log(self, task_id: str) -> bool:
        """
        清理指定任务的日志
        
        :param task_id: 任务ID
        :return: 是否清理成功
        """
        try:
            # 获取任务日志
            task = db.execute_sql(
                "SELECT log FROM task WHERE task_id = ?",
                params=[task_id],
                fetch="fetch_one"
            )
            
            if not task:
                logger.warning(f"任务不存在 | task_id: {task_id}")
                return False
            
            log_content = task.get('log', '')
            
            # 清理日志
            cleaned_log = self.clean_log(log_content)
            
            # 如果日志长度未超过阈值，不更新
            if len(log_content) <= self.char_threshold:
                return False
            
            # 更新数据库
            success = db.execute_sql(
                "UPDATE task SET log = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                params=[cleaned_log, task_id],
                fetch="none"
            )
            
            if success:
                logger.info(f"任务日志清理成功 | task_id: {task_id} | 原长度: {len(log_content)} | 新长度: {len(cleaned_log)}")
                return True
            else:
                logger.error(f"任务日志清理失败 | task_id: {task_id}")
                return False
                
        except Exception as e:
            logger.error(f"清理任务日志异常 | task_id: {task_id} | 错误: {e}", exc_info=True)
            return False
    
    def clean_all_logs(self) -> int:
        """
        清理所有超过阈值的任务日志
        
        :return: 清理的任务数量
        """
        if not self.auto_clean_enabled:
            logger.info("日志自动清理未启用，跳过清理")
            return 0
        
        try:
            # 获取所有需要清理的任务
            tasks = db.execute_sql(
                f"SELECT task_id, log FROM task WHERE length(log) > {self.char_threshold}",
                fetch="fetch"
            )
            
            if not tasks:
                logger.info("没有需要清理的任务日志")
                return 0
            
            cleaned_count = 0
            
            for task in tasks:
                task_id = task['task_id']
                log_content = task.get('log', '')
                
                # 清理日志
                cleaned_log = self.clean_log(log_content)
                
                # 更新数据库
                success = db.execute_sql(
                    "UPDATE task SET log = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                    params=[cleaned_log, task_id],
                    fetch="none"
                )
                
                if success:
                    cleaned_count += 1
                    logger.info(f"任务日志清理成功 | task_id: {task_id} | 原长度: {len(log_content)} | 新长度: {len(cleaned_log)}")
            
            logger.info(f"日志批量清理完成 | 共清理 {cleaned_count} 个任务")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"批量清理任务日志异常 | 错误: {e}", exc_info=True)
            return 0
    
    def check_and_clean_log(self, task_id: str) -> bool:
        """
        检查并清理任务日志（对外接口）
        
        :param task_id: 任务ID
        :return: 是否执行了清理
        """
        if not self.auto_clean_enabled:
            return False
        
        return self.clean_task_log(task_id)


class LogCleanerExecutor:
    """日志清理执行器 - 单独线程定期检测"""
    
    def __init__(self, check_interval: int = 300):
        """
        初始化日志清理执行器
        
        :param check_interval: 检查间隔（秒），默认300秒（5分钟）
        """
        self.check_interval = check_interval
        self.log_cleaner = LogCleaner()
        self.running = False
        self.thread = None
        
    def start(self):
        """启动日志清理执行器"""
        if self.running:
            logger.warning("日志清理执行器已在运行中")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("日志清理执行器已启动")
    
    def _run(self):
        """日志清理执行器运行方法"""
        while self.running:
            try:
                self.check_and_clean_logs()
            except Exception as e:
                logger.error(f"日志清理执行器异常: {e}", exc_info=True)
            
            # 使用可中断的睡眠，每秒检查一次是否需要退出
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def stop(self):
        """停止日志清理执行器"""
        if not self.running:
            logger.info("日志清理执行器未在运行，无需停止")
            return
            
        self.running = False
        logger.info("日志清理执行器已发出停止信号")
        
        # 等待线程退出
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning("日志清理执行器线程停止超时")
            else:
                logger.info("日志清理执行器线程已停止")
    
    def check_and_clean_logs(self):
        """检查并清理需要清理的日志"""
        try:
            # 检查是否启用自动清理
            if not self.log_cleaner.auto_clean_enabled:
                logger.info("日志自动清理未启用，跳过检查")
                return
            
            # 获取需要清理的任务
            tasks = db.execute_sql(
                f"SELECT task_id, log FROM task WHERE length(log) > {self.log_cleaner.char_threshold}",
                fetch="fetch"
            )
            
            if not tasks:
                logger.info(f"没有需要清理的任务日志（阈值: {self.log_cleaner.char_threshold} 字符）")
                return
            
            logger.info(f"发现 {len(tasks)} 个需要清理的任务日志")
            
            cleaned_count = 0
            
            for idx, task in enumerate(tasks, 1):
                task_id = task['task_id']
                log_content = task.get('log', '')
                original_length = len(log_content)
                
                # 清理日志
                cleaned_log = self.log_cleaner.clean_log(log_content)
                
                # 更新数据库
                success = db.execute_sql(
                    "UPDATE task SET log = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                    params=[cleaned_log, task_id],
                    fetch="none"
                )
                
                if success:
                    cleaned_count += 1
                    logger.info(f"任务日志清理成功 | task_id: {task_id} | 原长度: {original_length} | 新长度: {len(cleaned_log)}")
                else:
                    logger.error(f"任务日志清理失败 | task_id: {task_id}")
            
            logger.info(f"日志批量清理完成 | 共清理 {cleaned_count}/{len(tasks)} 个任务")
                    
        except Exception as e:
            logger.error(f"检查日志清理失败: {e}", exc_info=True)
    
    def reload_config(self):
        """重新加载配置"""
        self.log_cleaner.load_config()
        logger.info("日志清理器配置已重新加载")


# 全局日志清理器实例
log_cleaner: Optional[LogCleaner] = None
log_cleaner_executor: Optional[LogCleanerExecutor] = None


def get_log_cleaner() -> LogCleaner:
    """获取全局日志清理器实例"""
    global log_cleaner
    
    if log_cleaner is None:
        log_cleaner = LogCleaner()
    
    return log_cleaner


def get_log_cleaner_executor() -> LogCleanerExecutor:
    """获取全局日志清理执行器实例"""
    global log_cleaner_executor
    
    if log_cleaner_executor is None:
        log_cleaner_executor = LogCleanerExecutor(check_interval=300)
    
    return log_cleaner_executor


def reload_log_cleaner_config():
    """重新加载日志清理器配置"""
    global log_cleaner, log_cleaner_executor
    
    if log_cleaner is not None:
        log_cleaner.load_config()
        logger.info("日志清理器配置已重新加载")
    
    if log_cleaner_executor is not None:
        log_cleaner_executor.reload_config()
        logger.info("日志清理执行器配置已重新加载")


def start_log_cleaner_executor():
    """启动全局日志清理执行器"""
    global log_cleaner_executor
    
    if log_cleaner_executor is None:
        log_cleaner_executor = LogCleanerExecutor(check_interval=300)
        # 直接启动线程，不通过任务管理器
        log_cleaner_executor.start()
        logger.info("全局日志清理执行器已启动")


def stop_log_cleaner_executor():
    """停止全局日志清理执行器"""
    global log_cleaner_executor
    
    if log_cleaner_executor is not None:
        log_cleaner_executor.stop()
        log_cleaner_executor = None
        logger.info("全局日志清理执行器已停止")


if __name__ == "__main__":
    # 测试日志清理器
    cleaner = LogCleaner()
    
    # 测试清理日志
    test_log = "这是一条很长的日志内容\n" * 10000
    print(f"原日志长度: {len(test_log)}")
    
    cleaned_log = cleaner.clean_log(test_log)
    print(f"清理后日志长度: {len(cleaned_log)}")
    print(f"清理后日志前100字符: {cleaned_log[:100]}")
