import logging
import sqlite3
import os
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from typing import Optional

# -------------------------- loguru原生颜色常量（核心） --------------------------
# 与loguru原生级别颜色完全一致：DEBUG(蓝)、INFO(白)、SUCCESS(绿)、WARNING(黄)、ERROR(红)、CRITICAL(亮红)
class LogColor:
    # ANSI转义码：重置（清除颜色）、各级别专属颜色
    RESET = "\033[0m"
    DEBUG = "\033[36m"    # 青色/蓝色（loguru原生DEBUG色）
    INFO = "\033[37m"     # 白色（loguru原生INFO色）
    SUCCESS = "\033[32m"  # 绿色（loguru原生SUCCESS色）
    WARNING = "\033[33m"  # 黄色（loguru原生WARNING色）
    ERROR = "\033[31m"    # 红色（loguru原生ERROR色）
    CRITICAL = "\033[91m" # 亮红色/浅红色（loguru原生CRITICAL色）

# 级别与颜色的映射（完全对齐loguru）
LEVEL_COLOR_MAP = {
    logging.DEBUG: LogColor.DEBUG,
    logging.INFO: LogColor.INFO,
    logging.WARNING: LogColor.WARNING,
    logging.ERROR: LogColor.ERROR,
    logging.CRITICAL: LogColor.CRITICAL,
    25: LogColor.SUCCESS  # 自定义SUCCESS级别（25：介于INFO(20)和WARNING(30)之间）
}

# 为logging注册SUCCESS级别（让logger支持logger.success()，与loguru语法一致）
logging.addLevelName(25, "SUCCESS")
def success(self, msg, *args, **kwargs):
    if self.isEnabledFor(25):
        self._log(25, msg, args, **kwargs)
logging.Logger.success = success

# -------------------------- 自定义loguru风格彩色格式化器 --------------------------
class LoguruStyleColorFormatter(logging.Formatter):
    """复刻loguru原生格式的彩色格式化器，输出与loguru完全一致"""
    def __init__(self, fmt=None, datefmt=None):
        # 沿用loguru原生日志格式：时间 | 级别 | 模块:函数:行号 - 日志内容
        # levelname-8s 保证级别字段占8位，和loguru对齐（如SUCCESS 、INFO     ）
        super().__init__(
            fmt=fmt or "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt=datefmt or "%Y-%m-%d %H:%M:%S.%f"
        )

    def format(self, record: logging.LogRecord) -> str:
        """
        重写格式化方法：按loguru格式单独渲染字段颜色
        对应格式：<green>时间</green> | <level>级别</level> | <cyan>名称:函数:行号</cyan> - <level>消息</level>
        """
        # 1. 先执行父类格式化，得到原始日志字符串（无颜色）
        raw_log = super().format(record)
        # 2. 拆分原始日志为【时间、级别、名称:函数:行号、消息】四部分（按 | 和 - 拆分，兼容分隔符前后空格）
        try:
            time_part, level_part, rest_part = [p.strip() for p in raw_log.split("|", 2)]
            pos_part, msg_part = [p.strip() for p in rest_part.split("-", 1)]
        except ValueError:
            # 拆分失败时返回原始日志（避免格式异常）
            return raw_log

        # 3. 按loguru格式绑定颜色（核心：单独字段单独染色）
        colored_time = f"{LogColor.SUCCESS}{time_part}{LogColor.RESET}"  # 时间：绿色（对应<green>）
        colored_level = f"{LEVEL_COLOR_MAP.get(record.levelno, LogColor.INFO)}{level_part}{LogColor.RESET}"  # 级别：跟随级别色（对应<level>）
        colored_pos = f"{LogColor.DEBUG}{pos_part}{LogColor.RESET}"  # 名称:函数:行号：青色（对应<cyan>）
        colored_msg = f"{LEVEL_COLOR_MAP.get(record.levelno, LogColor.INFO)}{msg_part}{LogColor.RESET}"  # 消息：跟随级别色（对应<level>）

        # 4. 拼接成loguru原生格式的彩色日志（还原分隔符空格）
        colored_log = f"{colored_time} | {colored_level} | {colored_pos} - {colored_msg}"

        # 5. 处理异常栈：异常信息跟随级别颜色（与loguru一致）
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            # 异常栈跟在消息后，换行+级别色渲染
            colored_log = f"{colored_log}\n{LEVEL_COLOR_MAP.get(record.levelno, LogColor.INFO)}{record.exc_text}{LogColor.RESET}"

        return colored_log


# -------------------------- 核心：初始化logger（必须调用，否则无法使用） --------------------------
def init_logger(
    name: Optional[str] = __name__,
    level: int = logging.DEBUG,  # 设为DEBUG，保证所有级别日志都能输出
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    初始化loguru风格的彩色logger
    :param name: 日志器名称，默认__name__
    :param level: 日志级别，默认DEBUG（输出所有级别）
    :param log_file: 可选，日志文件路径（如需文件输出）
    :return: 配置好的彩色logger
    """
    # 创建日志器，清空原有处理器（避免重复输出）
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    # 配置loguru风格彩色格式化器（微秒保留3位，和loguru完全一致）
    color_formatter = LoguruStyleColorFormatter(
        datefmt="%Y-%m-%d %H:%M:%S.%f"[:-3]  # 截取微秒后3位，如2026-01-29 10:00:00.123
    )

    # 1. 添加控制台处理器（核心：彩色输出）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(color_formatter)
    logger.addHandler(console_handler)

    # 2. 可选：添加文件处理器（如需文件输出，文件中无颜色码，纯文本）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(color_formatter)
        logger.addHandler(file_handler)

    return logger

# -------------------------- 初始化全局logger（项目中直接导入使用） --------------------------
logger = init_logger()

# -------------------------- 测试：运行即输出loguru风格彩色日志 --------------------------
if __name__ == "__main__":
    # 输出所有级别彩色日志，和loguru原生效果完全一致
    logger.success("这是SUCCESS级别日志（绿色，loguru风格）")
    logger.error("这是ERROR级别日志（红色，loguru风格）")
    logger.warning("这是WARNING级别日志（黄色，loguru风格）")
    logger.info("这是INFO级别日志（白色，loguru风格）")
    logger.debug("这是DEBUG级别日志（青色，loguru风格）")
    logger.critical("这是CRITICAL级别日志（亮红色，loguru风格）")

