import time

from PyQt5.QtCore import QThread, pyqtSignal, QMutex
from loguru import logger

from lite_modules.LittleTools import check_date_validation_by_config


class DateCheckThread(QThread):
    # 定义“到期信号”：无参数，兼容你的原有逻辑
    expire_signal = pyqtSignal()
    # 线程安全锁：避免多线程操作stop_flag导致竞态问题
    _mutex = QMutex()

    def __init__(self):
        super().__init__()
        self.stop_flag = False

    def stop(self):
        """线程安全的停止方法"""
        self._mutex.lock()
        self.stop_flag = True
        self._mutex.unlock()

    def run(self):
        """线程执行逻辑：后台监测日期，到期发送信号"""
        # logger.info("日期监测线程启动")
        while True:
            # 先检查停止标志（优先退出）
            self._mutex.lock()
            if self.stop_flag:
                self._mutex.unlock()
                break
            self._mutex.unlock()

            try:
                # 调用你的日期验证函数（返回JSON格式结果）
                jsont = check_date_validation_by_config()

                # 检测到“到期/异常”（code≠1），发送信号给主线程
                if jsont.get('code') != 1:
                    self.expire_signal.emit()  # 发送信号（主线程接收后处理GUI）
                    logger.error(f"卡密验证失败：{jsont.get('msg')}")
                    break  # 发送信号后退出循环，线程结束

                # 每隔10秒监测一次（避免频繁调用接口）
                time.sleep(10)
            except Exception as e:
                err_msg = f"日期监测线程异常：{str(e)}"
                logger.error(err_msg)
                time.sleep(10)  # 异常时也延迟，避免死循环报错

            self.msleep(100)
        logger.info("日期监测线程已正常退出")