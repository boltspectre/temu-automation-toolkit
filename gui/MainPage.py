import ast
import re
import sys
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QComboBox, QLineEdit, QPushButton, QTextEdit, QLabel
)
from loguru import logger
from config.start_config import MAIN_TASK_MANAGER
from utils.multiThreading_manager import TaskStatus


def query_one_finance(platform, input_text, option):
    """模拟查询函数（已修复月份解析问题）"""
    # 1. 使用 split() 分割，它会自动处理多个连续空格
    parts = input_text.split()

    # 2. 确保至少有一个部分（店铺缩写）
    if not parts:
        return False, "输入内容不能为空！", []

    # 3. 第一个部分是 input_1 (店铺缩写)
    input_1 = parts[0]

    # 4. 如果有更多部分，将它们用空格重新连接起来作为 input_2 (月份字符串)
    #    如果没有，则 input_2 为 "未输入值"
    input_2 = " ".join(parts[1:]) if len(parts) > 1 else "未输入值"

    if platform == "添加账号":
        results = [{'platform': platform, 'name': input_1, 'password': input_2}]

    elif platform == "连接店铺":
        result = {'platform': platform}

        if len(input_1) > 5:
            result.update({'phone': input_1})
        else:
            result.update({'id': input_1})

        results = [result]

    elif platform == "生成店铺总数据结果":
        results = [{'platform': platform, 'name': input_1}]

    elif platform == "自动导出并计算财务汇总全流程任务":
        if '-' in input_2:
            month_result = f"{input_2.split('-')[0]}-{input_2.split('-')[1]}"
        else:
            # 1. 初步清理：移除所有空格和中文逗号
            clean_input = input_2.replace(" ", "").replace("，", ",")

            # 2. 按逗号分割成列表
            split_list = clean_input.split(',')

            # 3. 遍历列表，检查每个项是否符合格式，并排除空项
            valid_months = []
            # 定义一个正则表达式模式，用于匹配 "YYYY.M" 或 "YYYY.MM"
            month_pattern = re.compile(r'^\d{4}\.\d{1,2}$')

            for item in split_list:
                # 检查项是否为空，以及是否完全匹配月份格式
                if item and month_pattern.match(item):
                    valid_months.append(item)

            # 4. 去重：使用 dict.fromkeys() 可以在去重的同时保留原始顺序
            unique_months = list(dict.fromkeys(valid_months))

            # 5. 生成最终结果
            if unique_months:
                # 如果提取到了有效月份
                month_result = ",".join(unique_months)
            else:
                # 如果一个有效月份都没有提取到
                month_result = "月份:未找到任何有效的月份，请输入如 '2025.11,2025.02' 的格式。"
                logger.error(f"处理失败！提示: {month_result}")
                return False, month_result, [] # 如果需要返回值
        results = [{'platform': platform, 'name': input_1, 'months_list': month_result}]
    else:
        results = [{'platform': platform, 'name': input_1}]

    return True, "查询成功", results


class CheckableComboBox(QComboBox):
    """可复选的下拉框"""
    def __init__(self, parent=None):
        super(CheckableComboBox, self).__init__(parent)
        self.setModel(QStandardItemModel(self))
        self.view().viewport().installEventFilter(self)
        self._is_popup_open = False

    def eventFilter(self, source, event):
        if source == self.view().viewport() and event.type() == event.MouseButtonPress:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                item = self.model().itemFromIndex(index)
                if item.isCheckable():
                    item.setCheckState(Qt.Checked if item.checkState() == Qt.Unchecked else Qt.Checked)
                    return True
        return super(CheckableComboBox, self).eventFilter(source, event)

    def showPopup(self):
        self._is_popup_open = True
        super().showPopup()

    def hidePopup(self):
        if not self.view().underMouse():
            self._is_popup_open = False
            super().hidePopup()

    def mousePressEvent(self, event):
        if self.rect().contains(event.pos()) and event.button() == Qt.LeftButton:
            if self._is_popup_open:
                self.hidePopup()
            else:
                self.showPopup()
            event.accept()
        else:
            super().mousePressEvent(event)

    def checkedItems(self):
        return [self.model().item(i).text() for i in range(self.count()) if self.model().item(i).checkState() == Qt.Checked]


class SubmitTaskPage(QWidget):
    """
    独立的“提交任务”页面组件。
    """
    # 定义自定义信号：传递任务ID和结果
    task_finished_signal = pyqtSignal(str, dict)
    refresh_log_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_switched_to_multi_input = False # 初始化切换状态
        self.initUI()

        # 初始化定时器，用于轮询任务状态（间隔1秒）
        self.task_poll_timer = QTimer(self)
        self.task_poll_timer.setInterval(1000)
        self.task_poll_timer.timeout.connect(self.poll_task_status)
        # 存储需要轮询的任务ID
        self.pending_tasks = []
        # 连接信号到槽函数
        self.task_finished_signal.connect(self.handle_task_finished)

    def initUI(self):
        """初始化UI组件"""
        layout = QVBoxLayout(self)

        # 提交任务 GroupBox
        submit_group = QGroupBox("提交任务")
        submit_layout = QVBoxLayout()

        # 上方部分
        top_layout = QVBoxLayout()

        # 第一行：两个选择栏
        row1_layout = QHBoxLayout()
        self.platform_combo_one = QComboBox()
        self.platform_combo_one.addItems(["请选择任务类型"])

        # 使用统一的权限管理器加载权限
        from config.permission_manager import permission_manager
        code_project_mode = permission_manager.load_permissions()

        if "caiwu" in code_project_mode:
            self.platform_combo_one.addItems(["自动导出并计算财务汇总全流程任务", "生成财务总表"])

        if "spider" in code_project_mode:
            self.platform_combo_one.addItems(["关键词", "帖子ID", "虎扑评分", "url"])


        self.platform_combo_one.currentTextChanged.connect(self.update_input_placeholder)
        row1_layout.addWidget(self.platform_combo_one, stretch=85)

        self.option_combo_one = QComboBox()
        self.option_combo_one.addItems(["自动", "队列中"])
        row1_layout.addWidget(self.option_combo_one, stretch=10)
        top_layout.addLayout(row1_layout)

        # 第二行：输入栏和按钮
        self.row2_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("请选择任务类型")
        self.row2_layout.addWidget(self.input_edit, stretch=80)

        self.query_btn = QPushButton("查询")
        self.query_btn.clicked.connect(self.handleQuery_btn)
        # 注意：如果图标文件不存在，程序会运行但图标不显示，不会报错
        self.query_btn.setIcon(QIcon("./gui/img/sousuo.png"))
        self.row2_layout.addWidget(self.query_btn, stretch=10)

        self.switch_btn = QPushButton("切换")
        self.switch_btn.clicked.connect(self.handleSwitch_btn)
        self.switch_btn.setIcon(QIcon("./gui/img/qiehuan.png"))
        self.row2_layout.addWidget(self.switch_btn, stretch=10)
        top_layout.addLayout(self.row2_layout)

        row3_layout = QHBoxLayout()
        self.result_combo_one = CheckableComboBox()
        row3_layout.addWidget(self.result_combo_one)
        top_layout.addLayout(row3_layout)

        submit_layout.addLayout(top_layout)

        # 提交按钮和清空按钮
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)

        submit_btn = QPushButton("提交")
        submit_btn.clicked.connect(self.handleOneSubmit_btn)
        submit_btn.setIcon(QIcon("./gui/img/tijiao.png"))

        button_layout.addWidget(submit_btn)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clearInputs_one)
        clear_btn.setIcon(QIcon("./gui/img/qingli.png"))
        button_layout.addWidget(clear_btn)

        submit_layout.addLayout(button_layout)

        # 错误信息栏
        self.error_label_one = QLabel("")
        self.error_label_one.setAlignment(Qt.AlignCenter)
        self.error_label_one.setStyleSheet("color: red; font-weight: bold; font-size: 20px;")
        submit_layout.addWidget(self.error_label_one)

        submit_group.setLayout(submit_layout)
        layout.addWidget(submit_group)

        # 日志 GroupBox
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout()

        self.log_edit_one = QTextEdit()
        self.log_edit_one.setReadOnly(True)
        self.log_edit_one.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                color: #00BFFF;
                background-color: #F5F5F5;
            }
        """)
        self.log_edit_one.setPlaceholderText("提交日志将显示在这里")
        log_layout.addWidget(self.log_edit_one)

        # 添加清空按钮
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.refreshLogs_one)
        clear_log_btn.setIcon(QIcon("./gui/img/qingli.png"))
        log_layout.addWidget(clear_log_btn, alignment=Qt.AlignRight)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)


    def handleSwitch_btn(self):
        """处理输入框切换按钮"""
        if self.is_switched_to_multi_input:
            # 切换回单个输入框
            self.input_edit1.deleteLater()
            self.input_edit2.deleteLater()
            del self.input_edit1, self.input_edit2

            self.input_edit = QLineEdit()
            self.update_input_placeholder() # 切换后立即更新提示
            self.row2_layout.insertWidget(0, self.input_edit, stretch=80)
        else:
            # 切换到多个输入框
            self.input_edit.deleteLater()
            del self.input_edit

            self.input_edit1 = QLineEdit()
            self.input_edit2 = QLineEdit()
            self.update_input_placeholder() # 切换后立即更新提示
            self.row2_layout.insertWidget(0, self.input_edit1, stretch=40)
            self.row2_layout.insertWidget(1, self.input_edit2, stretch=40)

        self.is_switched_to_multi_input = not self.is_switched_to_multi_input
        self.update_input_placeholder()

    def update_input_placeholder(self):
        """根据选择的平台动态更新输入框的提示文字"""
        platform = self.platform_combo_one.currentText()

        # 定义一个字典来存储不同平台对应的提示文字
        # 键是平台名称，值是一个元组：(单个输入框提示, 第一个多输入框提示, 第二个多输入框提示)
        placeholders = {
            "请选择任务类型": ("请选择任务类型", "请选择任务类型", "请选择任务类型"),
            "添加账号": ("手机号 密码", "手机号", "密码"),
            "连接店铺": ("手机号 或 id", "手机号 或 id", "留空"),
            "生成财务总表": ("店铺缩写", "店铺缩写", "留空"),
            "自动导出并计算财务汇总全流程任务": ("店铺缩写 月份", "店铺缩写", "月份 (例如: 2025.1, 2025.02 或 2025.1-2025.10)"),
            "关键词": ("关键词 空格 页数", "关键词", "页数"),
            "帖子ID": ("帖子ID 空格 页数", "帖子ID", "页数"),
            "虎扑评分": ("虎扑评分ID或url 空格 页数", "评分ID或url", "页数"),
            "url": ("url 空格 页数", "url", "页数"),
        }

        # 获取对应的提示文字，如果平台不存在，则使用默认值
        single_ph, multi_ph1, multi_ph2 = placeholders.get(platform, ("请输入内容", "参数1", "参数2"))

        # 根据当前输入框的状态，设置相应的提示文字
        if self.is_switched_to_multi_input:
            if hasattr(self, 'input_edit1') and hasattr(self, 'input_edit2'):
                self.input_edit1.setPlaceholderText(multi_ph1)
                self.input_edit2.setPlaceholderText(multi_ph2)
        else:
            if hasattr(self, 'input_edit'):
                self.input_edit.setPlaceholderText(single_ph)


    def clearInputs_one(self):
        """清空所有输入控件的内容"""
        self.platform_combo_one.setCurrentIndex(0)
        self.option_combo_one.setCurrentIndex(0)
        self.error_label_one.setText("")
        self.result_combo_one.clear()

        if hasattr(self, 'input_edit'):
            self.input_edit.clear()
        if hasattr(self, 'input_edit1'):
            self.input_edit1.clear()
        if hasattr(self, 'input_edit2'):
            self.input_edit2.clear()

    def refreshLogs_one(self):
        """清空日志"""
        self.log_edit_one.setText("")
        self.refresh_log_signal.emit()

    def get_input_text(self):
        """根据当前状态获取输入文本"""
        if self.is_switched_to_multi_input:
            param = self.input_edit1.text().strip()
            page = self.input_edit2.text().strip()
            return f"{param} {page}" if param and page else param
        else:
            return self.input_edit.text().strip()

    def show_error(self, message):
        """显示错误信息"""
        self.error_label_one.setStyleSheet("color: red; font-weight: bold; font-size: 20px;")
        self.error_label_one.setText(message)

    def show_success(self, message):
        """显示成功信息"""
        self.error_label_one.setStyleSheet("color: #0bc008; font-weight: bold; font-size: 20px;")
        self.error_label_one.setText(message)

    def format_log(self, message, color="#666"):
        """格式化日志输出"""
        current_time = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        return f'<span style="color:#666">{current_time}</span><span style="color:{color}">{message}</span>'

    def poll_task_status(self):
        """
        轮询检查任务状态（已修改为使用 get_task_status）
        遍历 self.pending_tasks 列表，检查每个任务的状态。
        如果任务状态为 success, failed, 或 timeout，则认为任务已完成。
        """
        if not self.pending_tasks:
            self.task_poll_timer.stop()
            logger.info("✅ 所有任务已完成！")
            return

        # 遍历任务，检查是否完成
        finished_indices = []
        for idx, task_id in enumerate(self.pending_tasks):
            # 使用 get_task_status 获取任务的当前状态信息
            task_info = MAIN_TASK_MANAGER.get_task_status(task_id)

            # 如果任务信息存在，并且状态是完成状态
            if task_info and task_info['status'] in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT]:
                logger.info(f"任务 {task_id} 已完成，状态: {task_info['status']}")

                # 根据状态构建一个统一的结果字典
                if task_info['status'] == TaskStatus.SUCCESS:
                    # 如果任务函数返回了字典，直接使用它；否则包装成字典
                    if isinstance(task_info['result'], dict):
                        result = task_info['result']
                    else:
                        result = {"code": 1, "msg": str(task_info['result'])}
                else:  # FAILED 或 TIMEOUT
                    error_msg = task_info.get('error', f"任务状态为 {task_info['status']}")
                    result = {"code": -1, "msg": error_msg}

                # 任务已完成（成功/失败/超时），发送信号
                self.task_finished_signal.emit(task_id, result)
                finished_indices.append(idx)

        # 移除已完成的任务（倒序移除，避免索引错乱）
        for idx in reversed(finished_indices):
            self.pending_tasks.pop(idx)

    def handle_task_finished(self, task_id, result):
        """处理任务完成信号（运行在主线程，可安全更新UI）"""
        if result['code'] == 1:
            log_msg = f"任务 {task_id} 执行成功: {result['msg']}"
            self.log_edit_one.append(self.format_log(log_msg, color="#0bc008"))
        else:
            log_msg = f"任务 {task_id} 执行失败: {result['msg']}"
            self.log_edit_one.append(self.format_log(log_msg, color="#ff0000"))



if __name__ == "__main__":
    # 1. 初始化日志
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

    # 2. 创建 QApplication 实例
    app = QApplication(sys.argv)

    # 3. 设置全局字体（可选）
    font = QFont("Microsoft YaHei", 12)
    app.setFont(font)

    # 4. 创建一个主窗口 (QMainWindow)
    main_window = QMainWindow()
    main_window.setWindowTitle("ikun-TEMU财务报表数据处理")
    main_window.setGeometry(640, 230, 900, 660) # 设置窗口位置和大小

    # 5. 将 SubmitTaskPage 实例设置为主窗口的中央部件
    submit_page = SubmitTaskPage()
    main_window.setCentralWidget(submit_page)

    # 6. 显示主窗口
    main_window.show()

    # 7. 启动应用的事件循环
    sys.exit(app.exec_())