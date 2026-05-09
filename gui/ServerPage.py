import datetime
import multiprocessing
import os
import sys
import threading
import time

from PyQt5.QtCore import QSize, Qt, QMutex, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (QTextEdit, QVBoxLayout, QGroupBox, QComboBox,
                             QLabel, QLineEdit, QWidget, QHBoxLayout, QPushButton,
                             QApplication, QMessageBox, QCheckBox)
from loguru import logger

# 导入核心模块（确保路径正确）
from api.server_api import (
    start_cycle_thread, stop_cycle_thread,
    start_temu_task_process, stop_main_api_process,
)
from config.common_config import config_manager
from config.start_config import MAIN_TASK_MANAGER

# 全局互斥锁：防止并发操作启动/停止
operation_mutex = QMutex()

# 环境判断
is_nuitka = hasattr(sys, 'frozen') and 'nuitka' in sys.frozen.lower()
current_dir = os.path.dirname(os.path.abspath(__file__))

# 动态添加模块搜索路径
if is_nuitka:
    target_path = current_dir
else:
    target_path = os.path.dirname(current_dir)

if target_path not in sys.path:
    sys.path.insert(0, target_path)
else:
    sys.path.remove(target_path)
    sys.path.insert(0, target_path)


class StopServerThread(QThread):
    """异步停止服务器线程，避免阻塞主线程"""
    stop_finished = pyqtSignal(bool, str)  # 停止完成信号：(是否成功, 提示信息)
    log_update = pyqtSignal(str)  # 日志更新信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def run(self):
        """异步执行停止逻辑"""
        try:
            self.log_update.emit("开始停止服务器进程...")

            # 1. 停止周期线程（非阻塞）
            try:
                stop_cycle_thread()
                self.log_update.emit("周期线程停止指令已发送")
            except Exception as e:
                self.log_update.emit(f"<font color='orange'>周期线程停止警告</font>: {str(e)}")

            # 2. 停止主进程（带超时控制）
            try:
                # 启动一个子线程执行停止操作，避免阻塞
                stop_result = {"success": True, "msg": ""}

                def stop_process_async():
                    try:
                        stop_main_api_process(timeout=5)  # 新增超时参数（5秒）
                    except Exception as e:
                        stop_result["success"] = False
                        stop_result["msg"] = str(e)

                stop_thread = threading.Thread(target=stop_process_async)
                stop_thread.start()
                stop_thread.join(timeout=6)  # 等待6秒超时

                if stop_thread.is_alive():
                    self.log_update.emit("<font color='red'>进程停止超时，强制清理</font>")
                    stop_result["success"] = False
                    stop_result["msg"] = "停止超时"
                elif not stop_result["success"]:
                    self.log_update.emit(f"<font color='red'>进程停止失败</font>: {stop_result['msg']}")
                else:
                    self.log_update.emit("主进程已停止")
            except Exception as e:
                self.log_update.emit(f"<font color='red'>进程停止异常</font>: {str(e)}")
                stop_result["success"] = False

            # 3. 轻量级清理任务管理器（非阻塞）
            try:
                if hasattr(MAIN_TASK_MANAGER, 'clear_tasks'):
                    # 异步清理，不等待结果
                    threading.Thread(
                        target=MAIN_TASK_MANAGER.clear_tasks,
                        args=("ikun",),
                        daemon=True
                    ).start()
                    self.log_update.emit("任务管理器清理指令已发送")
            except Exception as e:
                self.log_update.emit(f"<font color='orange'>任务管理器清理警告</font>: {str(e)}")

            # 4. 最终状态通知
            if stop_result.get("success", False):
                self.stop_finished.emit(True, "服务器停止成功")
                self.log_update.emit("所有服务器资源已清理完成")
            else:
                self.stop_finished.emit(False, f"服务器停止不完全: {stop_result.get('msg', '未知错误')}")

        except Exception as e:
            self.log_update.emit(f"<font color='red'>停止逻辑异常</font>: {str(e)}")
            self.stop_finished.emit(False, f"停止失败: {str(e)}")


# ========== 原有ServerPage类修改 ==========
class ServerPage(QWidget):
    server_started = pyqtSignal()
    server_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 核心状态标记（加锁保护）
        self.is_running = False
        self.start_stop_lock = threading.Lock()
        self.stop_thread = None

        # 初始化UI
        self.setup_ui()

        # ========== 程序启动后自动重置按钮为启动状态 ==========
        self.reset_to_start_state()

        # ========== 异步清理残留进程/线程，确保状态一致 ==========
        self.clean_residual_resources()


        if config_manager.get_or_set_config("SettingPage_auto_run_server", "") == "是":
            # ========== 自动启动服务器（延迟1秒） ==========
            QTimer.singleShot(1000, self._auto_start_server)

    def _auto_start_server(self):
        """自动启动服务器（加锁保护，避免并发）"""
        with self.start_stop_lock:
            if not self.is_running:  # 确保只有未运行时才启动
                self._start_server()
                self.append_log("程序启动后自动触发服务器启动完成")

    def setup_ui(self):
        # 主布局
        main_layout = QVBoxLayout(self)

        # 服务器控制组框
        self.setup_server_groupbox()
        main_layout.addWidget(self.server_groupbox)

        # 日志组框
        self.setup_log_groupbox()
        main_layout.addWidget(self.log_groupbox)

        # 布局样式
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # 绑定信号槽
        self.start_btn.clicked.connect(self.on_start_btn_action)
        self.internal_ip_edit.textChanged.connect(self.on_internal_ip_edit_action)
        self.external_ip_edit.textChanged.connect(self.on_external_ip_edit_action)
        self.port_edit.textChanged.connect(self.on_port_edit_action)
        self.process_combo.currentIndexChanged.connect(self.on_process_combo_action)
        self.token_edit.textChanged.connect(self.on_token_edit_action)
        self.auth_checkbox.stateChanged.connect(self.on_auth_checkbox_action)
        self.thread_mode_combo.currentIndexChanged.connect(self.on_thread_mode_combo_action)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_combo_action)
        self.restart_combo.currentIndexChanged.connect(self.on_restart_combo_action)

        # 初始化配置
        self._init_config_ui()

    def _init_config_ui(self):
        """初始化UI配置（封装，便于维护）"""
        self.internal_ip_edit.setText(config_manager.get_or_set_config("ServerPage_internal_ip", "localhost"))
        self.external_ip_edit.setText(config_manager.get_or_set_config("ServerPage_external_ip", "localhost"))
        self.port_edit.setText(config_manager.get_or_set_config("ServerPage_port", "1234"))
        self.process_combo.setCurrentText(config_manager.get_or_set_config("ServerPage_process_count", "1"))
        self.token_edit.setText(config_manager.get_or_set_config("ServerPage_token", ""))
        self.auth_checkbox.setChecked(config_manager.get_or_set_config("ServerPage_auth", "False").lower() == "true")

        # 下拉框初始化
        try:
            thread_idx = int(config_manager.get_or_set_config("ServerPage_thread_mode", "0"))
            self.thread_mode_combo.setCurrentIndex(thread_idx)
        except ValueError:
            self.thread_mode_combo.setCurrentIndex(0)

        try:
            mode_idx = int(config_manager.get_or_set_config("ServerPage_mode", "0"))
            self.mode_combo.setCurrentIndex(mode_idx)
        except ValueError:
            self.mode_combo.setCurrentIndex(0)

        # 修复重启间隔的配置加载逻辑
        restart_interval_value = config_manager.get_or_set_config("ServerPage_restart_interval", "不重启")
        # 尝试按索引值处理（向后兼容）
        try:
            restart_idx = int(restart_interval_value)
            self.restart_combo.setCurrentIndex(restart_idx)
        except ValueError:
            # 如果不是数字，则按文本值查找匹配
            idx = self.restart_combo.findText(restart_interval_value)
            if idx != -1:
                self.restart_combo.setCurrentIndex(idx)
            else:
                # 默认选择"不重启"
                self.restart_combo.setCurrentIndex(0)

    def setup_server_groupbox(self):
        """设置服务器分组框"""
        self.server_groupbox = QGroupBox("服务器")
        layout = QVBoxLayout()

        # 第一行：启动按钮 + IP + 端口 + 进程数
        row1_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动")
        self.start_btn.setIcon(QIcon("gui/img/qidong.png"))
        self.start_btn.setStyleSheet("QPushButton { font-size: 25px; }")
        self.start_btn.setIconSize(QSize(32, 32))
        row1_layout.addWidget(self.start_btn)

        # 内网IP
        row1_layout.addWidget(QLabel("内网IP:"))
        self.internal_ip_edit = QLineEdit()
        self.internal_ip_edit.setPlaceholderText("192.168.0.1")
        self.internal_ip_edit.setFixedWidth(200)
        row1_layout.addWidget(self.internal_ip_edit)

        # 外网IP
        row1_layout.addWidget(QLabel("公网IP:"))
        self.external_ip_edit = QLineEdit()
        self.external_ip_edit.setPlaceholderText("localhost")
        self.external_ip_edit.setFixedWidth(220)
        row1_layout.addWidget(self.external_ip_edit)

        # 端口
        row1_layout.addWidget(QLabel("端口:"))
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("1234")
        self.port_edit.setFixedWidth(120)
        row1_layout.addWidget(self.port_edit)

        # 进程数
        row1_layout.addWidget(QLabel("进程数:"))
        self.process_combo = QComboBox()
        self.process_combo.addItems(["1", "2", "4", "8", "16"])
        row1_layout.addWidget(self.process_combo)
        row1_layout.addStretch()
        layout.addLayout(row1_layout)

        # 第二行：Token + 线程模式 + 运行模式 + 重启间隔
        row2_layout = QHBoxLayout()
        row2_layout.addWidget(QLabel("Token:"))
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("输入认证token")
        self.token_edit.setFixedWidth(220)
        row2_layout.addWidget(self.token_edit)

        row2_layout.addWidget(QLabel("启用认证:"))
        self.auth_checkbox = QCheckBox()
        self.auth_checkbox.setFixedWidth(80)
        row2_layout.addWidget(self.auth_checkbox)

        row2_layout.addWidget(QLabel("线程模式:"))
        self.thread_mode_combo = QComboBox()
        self.thread_mode_combo.addItems(["线程池", "动态线程池"])
        row2_layout.addWidget(self.thread_mode_combo)

        row2_layout.addWidget(QLabel("模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["自动", "待处理", "队伍中"])
        row2_layout.addWidget(self.mode_combo)

        row2_layout.addWidget(QLabel("重启:"))
        self.restart_combo = QComboBox()
        self.restart_combo.addItems(["不重启", "0.5小时", "1小时", "2小时", "4小时", "6小时", "12小时"])
        row2_layout.addWidget(self.restart_combo)
        row2_layout.addStretch()
        layout.addLayout(row2_layout)

        self.server_groupbox.setLayout(layout)

    def reset_to_start_state(self):
        """强制将按钮重置为启动状态（文字、图标、状态标记）"""
        with self.start_stop_lock:
            # 1. 同步逻辑状态
            self.is_running = False

            # 2. 同步UI状态（主线程执行，避免QT信号槽问题）
            self.start_btn.setText("启动")
            self.start_btn.setIcon(QIcon("gui/img/qidong.png"))  # 启动图标
            self.start_btn.setEnabled(True)  # 确保按钮可点击
            self.start_btn.setStyleSheet("QPushButton { font-size: 25px; }")  # 恢复样式

            # 3. 日志记录
            # self.append_log("程序初始化完成，按钮已重置为启动状态")

    def clean_residual_resources(self):
        """异步清理残留的进程/线程，确保状态一致"""

        def _clean():
            try:
                # 清理残留进程
                stop_main_api_process(timeout=3)
                # 清理残留线程
                stop_cycle_thread()
                # 清理任务管理器
                if hasattr(MAIN_TASK_MANAGER, 'clear_tasks'):
                    MAIN_TASK_MANAGER.clear_tasks("ikun")
                # self.append_log("残留进程/线程已清理，确保启动状态纯净")
            except Exception as e:
                self.append_log(f"<font color='orange'>清理残留资源警告</font>: {str(e)}")

        # 异步执行，不阻塞UI初始化
        threading.Thread(target=_clean, daemon=True).start()


    def setup_log_groupbox(self):
        """设置日志分组框"""
        self.log_groupbox = QGroupBox("日志")
        layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # self.log_text.setStyleSheet("QTextEdit { background-color: #f5f5f5; border: none; }")
        self.log_text.setStyleSheet("""
               QTextEdit {
                   border: 1px solid #ddd;
                   color: #00BFFF;
                   background-color: #F5F5F5;
               }
           """)
        self.log_text.setPlaceholderText("服务器日志将显示在这里...")
        layout.addWidget(self.log_text)

        # 清空按钮
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self.log_text.clear)
        clear_btn.setIcon(QIcon("gui/img/qingli.png"))
        layout.addWidget(clear_btn, alignment=Qt.AlignRight)

        self.log_groupbox.setLayout(layout)

    def on_start_btn_action(self):
        """处理启动/停止按钮点击（核心修复：加锁 + 去重 + 状态同步）"""
        # 加锁：防止并发点击导致重复操作
        with self.start_stop_lock:
            if not self.is_running:
                self._start_server()
            else:
                self._stop_server()

    def _start_server(self):
        """启动服务器（封装启动逻辑，便于维护）"""
        # 1. 参数校验
        external_ip = self.external_ip_edit.text().strip() or "0.0.0.0"
        port_text = self.port_edit.text().strip()
        process_count_text = self.process_combo.currentText()
        restart_interval = self.restart_combo.currentText()

        # 端口合法性校验
        try:
            port = int(port_text)
            if not (1 <= port <= 65535):
                QMessageBox.warning(self, "错误", "端口必须在1-65535之间！")
                return
        except ValueError:
            QMessageBox.warning(self, "错误", "端口必须是数字！")
            return

        # 进程数合法性校验
        try:
            process_count = int(process_count_text)
            if process_count < 1:
                QMessageBox.warning(self, "错误", "进程数必须≥1！")
                return
        except ValueError:
            QMessageBox.warning(self, "错误", "进程数必须是数字！")
            return

        # 2. 更新UI状态
        self.start_btn.setText("停止")
        self.start_btn.setIcon(QIcon("gui/img/tingzhi.png"))
        self.is_running = True

        # 3. 输出启动日志
        self.append_log("服务器启动中")
        self.append_log(f"注意: 本地测试请填写 localhost，端口避免冲突（如3306/8080）")
        self.append_log(f"注意: 服务器部署请填写公网IP；公网ip填写0.0.0.0则会自动监听所有网卡，不知道公网ip可以填写0.0.0.0或局域网ip")
        self.append_log(f"重启间隔: {restart_interval} | Token: {self.token_edit.text()} | 启用认证: {'是' if self.auth_checkbox.isChecked() else '否'}")
        self.append_log(f"线程模式: {self.thread_mode_combo.currentText()} | 运行模式: {self.mode_combo.currentText()}")

        # 计算端口列表
        port_list = [str(port + i) for i in range(process_count)]

        host_url = external_ip if external_ip != "0.0.0.0" else '127.0.0.1'
        self.append_log(f"进程数: {process_count} | 可用端口: {', '.join(port_list)}")
        self.append_log(f"WEB端: http://{host_url}:{port}?token={self.token_edit.text()}")
        self.append_log(f"API接口文档: http://{host_url}:{port}/docs")

        # 4. 启动服务器（仅执行一次，避免重复）
        try:
            # 先停止残留进程（异步，不阻塞启动）
            threading.Thread(
                target=self._clean_residual_process,
                daemon=True
            ).start()

            # 启动主进程
            MAIN_TASK_MANAGER.add_task(
                task_id=f"服务器启动任务",
                target_func=self.start_server_reactor,
                task_group="ikun",
            )

            # 启动周期线程（如果需要重启）
            if restart_interval != "不重启":
                MAIN_TASK_MANAGER.add_task(
                    task_id=f"服务器定时重启任务",
                    target_func=start_cycle_thread,
                    task_group="ikun",
                )

            self.append_log("服务器正在运行...")
        except Exception as e:
            self.append_log(f"<font color='red'>启动失败</font>: {str(e)}")
            logger.error(f"服务器启动失败: {e}", exc_info=True)
            # 恢复UI状态
            self.reset_to_start_state()

    def _clean_residual_process(self):
        """异步清理残留进程（启动前）"""
        try:
            stop_main_api_process(timeout=3)
            stop_cycle_thread()
        except Exception as e:
            logger.warning(f"清理残留进程失败: {e}")

    def _stop_server(self):
        """停止服务器（异步化修改）"""
        # 1. 立即更新UI状态，避免用户感知阻塞
        self.start_btn.setText("停止中")
        self.start_btn.setEnabled(False)
        self.append_log("开始异步停止服务器...")

        # 2. 创建并启动停止线程
        self.stop_thread = StopServerThread(self)
        self.stop_thread.stop_finished.connect(self.on_stop_finished)
        self.stop_thread.log_update.connect(self.append_log)
        self.stop_thread.start()

    def on_stop_finished(self, success, msg):
        """停止完成回调（主线程执行）"""
        self.reset_to_start_state()
        self.server_stopped.emit()

        # 提示结果
        if success:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "警告", msg)


    def start_server_reactor(self):
        """启动服务器核心逻辑（单例执行）"""
        try:
            # 确保全局进程列表为空
            global main_gui_process
            main_gui_process = []

            # 启动定时任务执行器
            try:
                from utils.scheduled_task_executor import start_scheduled_task_executor
                start_scheduled_task_executor()
                self.append_log("定时任务执行器已启动")
            except Exception as e:
                self.append_log(f"<font color='red'>定时任务执行器启动失败</font>: {str(e)}")
                logger.error(f"定时任务执行器启动失败: {e}", exc_info=True)

            # 启动FastAPI服务（这个函数会启动多进程，不会阻塞）
            start_temu_task_process()
            
            # 启动流程最后触发"服务器已启动"信号，交由主窗口决定何时显示内嵌页
            self.server_started.emit()

        except Exception as e:
            self.append_log(f"<font color='red'>进程启动异常</font>: {str(e)}")
            logger.error(f"start_server_reactor异常: {e}", exc_info=True)
            # 恢复状态
            self.reset_to_start_state()

    def stop_server_reactor(self):
        """原有停止逻辑（保留，供任务管理器调用）"""
        try:
            # 1. 停止定时任务执行器
            try:
                from utils.scheduled_task_executor import stop_scheduled_task_executor
                stop_scheduled_task_executor()
                self.append_log("定时任务执行器已停止")
            except Exception as e:
                self.append_log(f"<font color='red'>定时任务执行器停止失败</font>: {str(e)}")
                logger.error(f"定时任务执行器停止失败: {e}", exc_info=True)

            # 2. 停止所有主进程（带超时）
            stop_main_api_process(timeout=5)

            # 3. 停止周期线程
            stop_cycle_thread()

            # 4. 清理任务管理器
            if hasattr(MAIN_TASK_MANAGER, 'clear_tasks'):
                MAIN_TASK_MANAGER.clear_tasks(task_group="ikun")

            self.append_log("所有进程/线程已彻底清理")
        except Exception as e:
            self.append_log(f"<font color='red'>进程停止异常</font>: {str(e)}")
            logger.error(f"stop_server_reactor异常: {e}", exc_info=True)

    def append_log(self, message):
        """添加日志记录"""
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        self.log_text.append(f'{timestamp}{message}')
        # 延迟滚动到最新日志，确保UI刷新
        QTimer.singleShot(10, lambda: self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()))

    # 配置保存槽函数（无修改，仅格式优化）
    # 注意：需要先确保已初始化 config_manager（建议在 ServerPage 初始化时传入）
    def on_internal_ip_edit_action(self, text):
        """内网IP修改：保存到数据库"""
        config_manager.upsert_config("ServerPage_internal_ip", text)

    def on_external_ip_edit_action(self, text):
        """外网IP修改：保存到数据库"""
        config_manager.upsert_config("ServerPage_external_ip", text)

    def on_port_edit_action(self, text):
        """端口修改：保存到数据库"""
        config_manager.upsert_config("ServerPage_port", text)

    def on_process_combo_action(self):
        """进程数修改：保存到数据库"""
        process_count = self.process_combo.currentText()
        config_manager.upsert_config("ServerPage_process_count", process_count)

    def on_token_edit_action(self, text):
        """Token修改：保存到数据库"""
        config_manager.upsert_config("ServerPage_token", text)

    def on_auth_checkbox_action(self, state):
        """认证开关修改：保存到数据库"""
        config_manager.upsert_config("ServerPage_auth", "true" if state == 2 else "False")

    def on_thread_mode_combo_action(self, index):
        """线程模式修改：保存到数据库（存储索引值）"""
        thread_mode = str(index)
        config_manager.upsert_config("ServerPage_thread_mode", thread_mode)

    def on_mode_combo_action(self, index):
        """运行模式修改：保存到数据库（存储索引值）"""
        mode = str(index)
        config_manager.upsert_config("ServerPage_mode", mode)

    def on_restart_combo_action(self, index):
        """重启间隔修改：保存到数据库（存储实际值，如"1小时"）"""
        restart_interval = self.restart_combo.currentText()
        config_manager.upsert_config("ServerPage_restart_interval", restart_interval)

    # 窗口关闭时的清理逻辑
    def closeEvent(self, event):
        """窗口关闭时彻底停止所有进程/线程"""
        if self.is_running:
            # 异步停止，不阻塞关闭
            self._stop_server()
            # 短暂等待停止线程启动
            time.sleep(0.1)
        self.reset_to_start_state()
        event.accept()


if __name__ == "__main__":
    # 多进程支持（Windows必须）
    multiprocessing.freeze_support()

    app = QApplication(sys.argv)
    window = ServerPage()
    window.show()

    # 设置全局字体
    font = QFont("Microsoft YaHei", 12)
    app.setFont(font)

    sys.exit(app.exec_())