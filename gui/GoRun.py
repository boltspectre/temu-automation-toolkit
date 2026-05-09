import sys

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QPushButton,
                             QLabel, QWidget, QMessageBox)
from loguru import logger

from modules.close_all import kill_other_python_processes


class GoProgramThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config, exe_path):
        super().__init__()
        self.config = config
        self.exe_path = exe_path
        self.process = None  # 添加process引用
        self.ziyan_console_mode = False
        logger.trace("初始化完成")

    def run(self):
        try:
            # 直接使用当前文件中定义的run_go_attack函数
            from pathlib import Path
            import subprocess
            import sys

            logger.trace(f"[DEBUG] 启动GO程序配置: {self.config}")
            go_exe = Path(self.exe_path)

            # 动态生成命令行参数
            args = [str(go_exe.absolute())]
            for key, value in self.config.items():
                if key == "no_proxy" and value:
                    args.append("--no-proxy")
                    continue
                if key == "console" and value:
                    self.ziyan_console_mode = value
                args.append(f"--{key.replace('_', '-')}={value}")

            # 打印将要执行的完整命令
            full_command = " ".join(args)
            logger.info(f"即将执行的命令: {full_command}")
            print(f"即将执行的命令: {full_command}")  # 同时打印到控制台

            if self.ziyan_console_mode:
                # 展示控制台
                self.process = subprocess.Popen(
                    args,
                    text=True,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                )
            else:
                self.process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                )
            logger.trace(f"攻击程序已启动，PID: {self.process.pid}")

            # 非阻塞读取输出
            while True:
                if self.process.stdout:
                    output = self.process.stdout.readline()
                    if output == '' and self.process.poll() is not None:
                        break
                else:
                    if self.process.poll() is not None:
                        break
                    QThread.msleep(100)

            # if self.process.returncode != 0:
            #     raise Exception(f"程序异常退出，返回值: {self.process.returncode}")

            self.finished_signal.emit(True, "退出成功")

        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def stop(self):
        """安全停止方法"""
        if self.process:
            self.process.terminate()


class ZiyanWindow(QMainWindow):
    def __init__(self, config, exe_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自研压测模型启动窗口")
        self.resize(500, 250)
        self.setWindowIcon(QIcon("gui/img/favicon.ico"))
        self.config = config
        self.exe_name = exe_name
        # 初始化UI
        self.init_ui()

        # 线程状态
        self.ziyan_is_started = False

    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()

        self.status_label = QLabel("准备就绪")
        self.start_btn = QPushButton("启动攻击")
        self.start_btn.clicked.connect(self.toggle_go_program)

        layout.addWidget(self.status_label)
        layout.addWidget(self.start_btn)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def toggle_go_program(self):
        if self.ziyan_is_started:
            self.stop_go_program()
        else:
            self.start_go_program()

    def start_go_program(self):
        """启动程序"""
        self.thread = GoProgramThread(self.config, self.exe_name)
        self.thread.finished_signal.connect(self.on_go_finished)
        self.thread.start()

        self.ziyan_is_started = True
        self.start_btn.setText("停止攻击")
        self.status_label.setText("运行中...")

    def stop_go_program(self):
        """停止程序"""
        if hasattr(self, 'thread') and self.thread.isRunning():
            # self.thread.stop()  # 调用新增的stop方法
            find_and_kill_ziyan_processes()
            self.ziyan_is_started = False
            self.start_btn.setText("启动程序")
            self.status_label.setText("程序已停止")

    def on_go_finished(self, success, message):
        """程序执行完成回调"""
        self.ziyan_is_started = False
        self.start_btn.setText("启动攻击")

        if success:
            self.status_label.setText("执行成功")
            QMessageBox.information(self, "成功", message)
        else:
            self.status_label.setText("执行失败")
            QMessageBox.critical(self, "错误", message)

    def closeEvent(self, event):
        """
        窗口关闭事件优化：
        1. 父窗口关闭触发时：跳过弹窗，直接关闭进程和窗口
        2. 用户手动关闭时：保留弹窗提示（原有逻辑）
        """
        # ---------------------- 新增：判断是否由父窗口关闭触发 ----------------------
        # 核心逻辑：若父窗口已关闭（或正在关闭），则跳过弹窗
        parent_closed = False
        if self.parent():  # 存在父窗口时才判断
            # 检查父窗口是否已隐藏/关闭（Qt 窗口关闭时会先隐藏再销毁）
            if not self.parent().isVisible():
                parent_closed = True

        # ---------------------- 原有逻辑适配 ----------------------
        if self.ziyan_is_started:
            # 情况1：父窗口已关闭 → 直接执行关闭（无弹窗）
            if parent_closed:
                self.stop_go_program()  # 终止进程
                event.accept()  # 关闭窗口
                if event:
                    event.accept()
                    kill_other_python_processes()
                return

            # 情况2：用户手动关闭 → 保留弹窗提示（原有逻辑）
            reply = QMessageBox.question(
                self,
                "确认关闭",
                "程序仍在运行中，关闭窗口将终止进程，是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.stop_go_program()
                event.accept()
            else:
                event.ignore()
        else:
            # 程序未运行 → 直接关闭（无论是否由父窗口触发）
            event.accept()

import psutil
def find_and_kill_ziyan_processes():
    # 查找所有名称包含"ziyan"的进程
    ziyan_processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'ziyan' in proc.info['name'].lower():
                ziyan_processes.append(proc)
                logger.trace(f"找到进程: PID={proc.info['pid']}, 名称={proc.info['name']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # 如果没有找到相关进程
    if not ziyan_processes:
        logger.trace("没有找到名称包含'ziyan'的进程")
        return

    # 关闭找到的所有进程
    for proc in ziyan_processes:
        try:
            proc.terminate()
            logger.trace(f"已终止进程: PID={proc.info['pid']}, 名称={proc.info['name']}")
        except Exception as e:
            logger.trace(f"终止进程失败(PID={proc.info['pid']}): {str(e)}")
