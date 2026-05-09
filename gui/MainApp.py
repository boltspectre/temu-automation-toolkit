import os
import platform
import subprocess
import sys
import time
import multiprocessing
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QGroupBox, QMessageBox, QToolButton, QButtonGroup, QStackedWidget, QLabel, QProgressBar, QDialog
)
from loguru import logger

from api.server_api import stop_main_api_process, stop_cycle_thread
from api.proxy_api import stop_proxy_api
from config.common_config import config_manager, global_db_close
from config.start_config import MAIN_TASK_MANAGER
from gui.HelpPage import HelpWindow
from gui.ProxyPage import ProxyPage
from gui.ServerPage import ServerPage
from gui.SettingPage import SettingWindow
from gui.SqlitePage import DbTableViewer, create_tab_config
from gui.ToolsPage import ToolsPage
from gui.utils.window_adapter import adapt_window_size
from lite_modules.DateCheckThread import DateCheckThread
from lite_modules.LittleTools import get_app_root_dir, adapt_component_size
from lite_modules.port_killer import self_pid_cleanup
from utils.multiThreading_log_manager import get_task_log_manager
from utils.directClient import auto_detect_and_clean_all_browsers


class ExitProgressDialog(QDialog):
    """程序退出进度弹窗，展示各清理步骤的状态"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 弹窗基础设置：无标题栏、模态、固定大小
        self.setWindowTitle("程序退出中")
        # self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)  # 无装饰边框
        self.setModal(True)  # 模态弹窗，阻塞主窗口
        self.setFixedSize(400, 150)  # 固定弹窗大小，避免拉伸
        self.center_window()  # 居中显示（相对主窗口）

        # 布局：垂直布局，包含状态文本和进度条
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignCenter)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(20)

        # 状态文本标签：显示当前执行步骤
        self.status_label = QLabel("准备执行退出流程...")
        self.status_label.setFont(QFont("微软雅黑", 12))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)

        # 进度条：0-100，逐步递增
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)  # 不显示进度百分比
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #0B78F4;
                width: 20px;
            }
        """)
        self.layout.addWidget(self.progress_bar)

        self.setLayout(self.layout)

    def center_window(self):
        """弹窗相对主窗口居中显示"""
        if self.parent():
            # 获取主窗口位置和大小
            parent_geo = self.parent().geometry()
            # 计算弹窗居中坐标
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(x, y)
        else:
            # 无主窗口则屏幕居中
            qr = self.frameGeometry()
            cp = QApplication.desktop().availableGeometry().center()
            qr.moveCenter(cp)
            self.move(qr.topLeft())

    def update_status(self, text, progress):
        """更新弹窗状态文本和进度条值"""
        self.status_label.setText(text)
        self.progress_bar.setValue(progress)
        # 强制刷新界面，确保状态实时显示（关键：避免界面卡顿）
        QApplication.processEvents()


# class WebPageView(QWidget):
#     """内嵌网页视图页面"""
#
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.page_loaded = False  # 标记页面是否已加载
#         self.init_ui()
#
#     def init_ui(self):
#         """初始化UI"""
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(0)
#
#         # 创建WebEngine视图
#         self.web_view = QWebEngineView()
#
#         # 创建提示标签
#         self.hint_label = QLabel("请在服务器页点击启动按钮")
#         self.hint_label.setAlignment(Qt.AlignCenter)
#         self.hint_label.setStyleSheet("""
#             QLabel {
#                 font-size: 30px;
#                 color: #666;
#                 padding: 50px;
#             }
#         """)
#
#         # 固定保留两个控件，通过显示/隐藏切换
#         layout.addWidget(self.hint_label)
#         layout.addWidget(self.web_view)
#         self.web_view.hide()
#
#         # 取消自动刷新，避免提交页嵌入网页在使用中被强制刷新
#         self.refresh_timer = QTimer()
#         self.refresh_timer.timeout.connect(self.refresh_page)
#         # self.refresh_timer.start(30000)  # 已禁用自动刷新
#
#     def _build_server_url(self):
#         from config.common_config import config_manager
#         external_ip = config_manager.get_or_set_config("ServerPage_external_ip", "localhost")
#         port = config_manager.get_or_set_config("ServerPage_port", "8888")
#         token = config_manager.get_or_set_config("ServerPage_token", "")
#
#         if external_ip == "0.0.0.0":
#             external_ip = "localhost"
#
#         return f"http://{external_ip}:{port}?token={token}"
#
#     def load_web_page(self):
#         """服务器启动完成后加载并显示网页"""
#         try:
#             url = self._build_server_url()
#             self.web_view.load(QUrl(url))
#             self.page_loaded = True
#             self.hint_label.hide()
#             self.web_view.show()
#         except Exception as e:
#             logger.error(f"加载提交页失败: {e}")
#             self.show_startup_hint()
#
#     def show_startup_hint(self):
#         """服务器停止后显示启动提示"""
#         self.page_loaded = False
#         self.web_view.setUrl(QUrl("about:blank"))
#         self.web_view.hide()
#         self.hint_label.setText("请在服务器页点击启动按钮")
#         self.hint_label.show()
#
#     def refresh_page(self):
#         """刷新页面（仅在需要时手动调用）"""
#         pass



class MainStartApp(QMainWindow):
    """
    应用程序的主框架。
    主界面固定显示"提交"页面（内嵌网页），其他功能通过点击按钮切换页面。
    """

    def closeEvent(self, event):
        """重写窗口关闭事件，增加退出确认、进度弹窗和任务清理逻辑"""
        exit_dialog = None  # 初始化变量，避免UnboundLocalError
        
        if self.close_confirm:
            # 第一步：退出确认弹窗
            reply = QMessageBox.question(
                self,
                '确认退出',
                '确定要退出程序吗？未完成的任务状态将会修改为已退出。',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

            # 第二步：实例化退出进度弹窗并显示（相对主窗口居中）
            exit_dialog = ExitProgressDialog(parent=self)
            exit_dialog.show()
        try:
            # 步骤1：初始化退出流程，更新进度
            if exit_dialog:
                exit_dialog.update_status("开始执行退出流程...", 10)
            # 清理未完成子任务
            get_task_log_manager().clean_all_unfinished_subtasks_on_start()

            # 步骤2：停止API进程，更新进度
            if exit_dialog:
                exit_dialog.update_status("正在停止主API进程...", 25)
            stop_main_api_process()
            
            if exit_dialog:
                exit_dialog.update_status("正在停止代理API进程...", 35)
            stop_proxy_api()
            # time.sleep(1)

            # 步骤3：停止循环线程，更新进度
            if exit_dialog:
                exit_dialog.update_status("正在停止循环任务线程...", 45)
            stop_cycle_thread()

            # 步骤4：停止任务管理器，更新进度
            # exit_dialog.update_status("正在关闭任务管理器...", 70)
            # if 'MAIN_TASK_MANAGER' in globals():
            #     MAIN_TASK_MANAGER.stop()

            # exit_dialog.update_status("正在关闭任务管理器...", 90)
            # if 'get_task_log_manager()' in globals():
            #     get_task_log_manager().stop()

            # 步骤5：关闭数据库（补充你实际的数据库关闭代码，若有封装函数直接调用）
            if exit_dialog:
                exit_dialog.update_status("正在安全关闭数据库，防止文件损坏...", 90)

            auto_detect_and_clean_all_browsers()
            global_db_close()

            # 步骤6：准备退出，更新进度
            if exit_dialog:
                exit_dialog.update_status("清理完成，即将退出程序...", 100)

            QApplication.processEvents()

            # 核心：接受关闭事件+退出应用
            event.accept()
            app = QApplication.instance()
            app.quit()

            # 退出前打印日志（避免在 quit 后打印导致 [Errno 22] 错误）
            try:
                print("程序已完全退出")
            except:
                pass

            # self_pid_cleanup(force_kill=False)

        except Exception as e:
            # 异常场景：更新弹窗状态，强制退出
            if exit_dialog:
                exit_dialog.update_status(f"退出过程出现异常，强制退出...{str(e)[:20]}", 100)
            get_task_log_manager().clean_all_unfinished_subtasks_on_start()
            QApplication.processEvents()
            # 异常时仍执行必要清理
            # if 'get_task_log_manager()' in globals():
            #     get_task_log_manager().stop()
            # 强制退出
            print(f"退出流程异常：{str(e)}")
            event.accept()
            app = QApplication.instance()
            app.quit()
        finally:
            # 确保弹窗关闭（无论正常/异常）
            if exit_dialog:
                exit_dialog.close()

    def __init__(self, project_debug=0, code_project_mode_debug=None):
        super().__init__()
        # 用于存储弹出的子窗口实例，防止被垃圾回收
        self.db_window = None
        self.help_window = None
        self.project_debug = project_debug
        self.code_project_mode_debug = code_project_mode_debug
        
        # 从系统配置读取关闭确认弹窗设置
        try:
            from config.common_config import config_manager
            if config_manager is not None:
                self.close_confirm = int(config_manager.get_or_set_config("close_confirm", "1"))
            else:
                self.close_confirm = 1  # 默认显示确认弹窗
        except Exception as e:
            print(f"读取关闭确认配置失败，使用默认值: {e}")
            self.close_confirm = 1  # 默认显示确认弹窗

        # 2. 初始化并启动日期监测线程
        self.date_check_thread = DateCheckThread()
        # 连接线程的“到期信号”到主线程的处理函数（关键：线程安全）
        self.date_check_thread.expire_signal.connect(self.handle_expire)
        # 启动线程
        self.date_check_thread.start()
        self.init_ui()

    def adapt_window_size(self):
        """动态适配窗口尺寸：以2560×1440的1650×600为基准"""
        adapt_window_size(self, 1650, 600)

    def init_ui(self):
        """初始化主窗口的UI布局"""
        if config_manager is not None:
            self.user_sign_name = config_manager.get_or_set_config(
                "user_sign_name",
                "我是真爱粉"
            )
        else:
            self.user_sign_name = "我是真爱粉"

        self.setWindowTitle(f"Ikun联盟 - {self.user_sign_name}")

        # 动态计算适配当前分辨率的窗口尺寸（替代固定self.resize(1650, 600)）
        self.adapt_window_size()  # 新增：动态适配尺寸
        # self.resize(1650, 600)
        self.center()

        try:
            self.setWindowIcon(QIcon("gui/img/favicon.ico"))
        except Exception as e:
            logger.warning(f"未找到图标文件 'favicon.ico': {e}")

        # 1. 创建中央部件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========== 新增：左侧内容区改为 堆叠窗口+底部按钮 的组合布局 ==========
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(10, 0, 10, 20)
        left_layout.setSpacing(20)  # 内容区和按钮栏之间留15px间距

        # 2. 左侧内容区：堆叠窗口（默认显示提交页面）
        self.stacked_widget = QStackedWidget()
        # 添加页面（保留原有提交页面，其他为空白占位页）
        # self.submit_task_page = SubmitTaskPage(parent=self)
        # self.start_page = StartPage()
        # self.web_page = WebPageView(parent=self)
        self.proxy_page = ProxyPage()
        self.server_page = ServerPage()
        self.toolbox_page = ToolsPage()

        # 提交页随服务器启动/停止联动
        # self.server_page.server_started.connect(self.web_page.load_web_page)
        # self.server_page.server_stopped.connect(self.web_page.show_startup_hint)


        # self.stacked_widget.addWidget(self.server_page)  # 0 - 服务器页面（第一位）
        # self.stacked_widget.addWidget(self.web_page)  # 1 - 提交任务页面（第二位）
        self.stacked_widget.addWidget(self.server_page)  # 0 - 服务器页面（第一位）
        # self.stacked_widget.addWidget(self.web_page)  # 1 - 提交任务页面（第二位）
        self.stacked_widget.addWidget(self.proxy_page)  # 2 - 代理IP页面（第三位）
        self.stacked_widget.addWidget(self.toolbox_page)  # 3 - 工具箱页面（第四位）

        left_layout.addWidget(self.stacked_widget, stretch=1)

        # ========== 新增：底部按钮栏 ==========
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 5, 0, 5)
        button_layout.setSpacing(0)  # 移除按钮间距

        button_size = adapt_component_size(28, 20)

        # 按钮样式
        button_style = f"""
        QToolButton {{
            border: 1px solid #ccc;
            border-right: none;
            padding: {button_size["h"]}px;
            background-color: white;
            font-size: {button_size["w"]}px;
            color: black;
        }}
        QToolButton:first-child {{
            border-top-left-radius: 5px;
            border-bottom-left-radius: 5px;
        }}
        QToolButton:last-child {{
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
            border-right: 1px solid #ccc;
        }}
        QToolButton:hover {{
            background-color: #f0f0f0;
        }}
        QToolButton:checked {{
            background-color: gold;
        }}
        """

        # 创建按钮组
        self.button_group = QButtonGroup()
        self.group_button_height = 80
        self.group_button_weight = 180
        group_button_size = adapt_component_size(self.group_button_weight, self.group_button_height)
        self.group_button_height = group_button_size['h']
        self.group_button_weight = group_button_size['w']

        self.button_group.setExclusive(True)

        # 创建按钮
        server_btn = QToolButton()
        server_btn.setText("启动")
        server_btn.setCheckable(True)
        server_btn.setFixedWidth(self.group_button_weight)
        server_btn.setFixedHeight(self.group_button_height)
        server_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        server_btn.setStyleSheet(button_style)
        self.button_group.addButton(server_btn)

        # submit_task_btn = QToolButton()
        # submit_task_btn.setText("提交")
        # submit_task_btn.setCheckable(True)
        # submit_task_btn.setFixedHeight(self.group_button_height)
        # submit_task_btn.setFixedWidth(self.group_button_weight)
        # submit_task_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        # submit_task_btn.setStyleSheet(button_style)
        # self.button_group.addButton(submit_task_btn)

        # batch_submit_btn = QToolButton()
        # batch_submit_btn.setText("批量提交")
        # batch_submit_btn.setCheckable(True)
        # batch_submit_btn.setFixedHeight(self.group_button_height)
        # batch_submit_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        # batch_submit_btn.setStyleSheet(button_style)
        # self.button_group.addButton(batch_submit_btn)

        # start_btn = QToolButton()
        # start_btn.setText("启动")
        # start_btn.setCheckable(True)
        # start_btn.setFixedWidth(self.group_button_weight)
        # start_btn.setFixedHeight(self.group_button_height)
        # start_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        # start_btn.setStyleSheet(button_style)
        # self.button_group.addButton(start_btn)

        proxy_btn = QToolButton()
        proxy_btn.setText("代理IP")
        proxy_btn.setCheckable(True)
        proxy_btn.setFixedWidth(self.group_button_weight)
        proxy_btn.setFixedHeight(self.group_button_height)
        proxy_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        proxy_btn.setStyleSheet(button_style)
        self.button_group.addButton(proxy_btn)

        # 删除原来的server_btn代码，因为已经移到前面了
        # server_btn = QToolButton()
        # server_btn.setText("服务器")
        # server_btn.setCheckable(True)
        # server_btn.setFixedWidth(self.group_button_weight)
        # server_btn.setFixedHeight(self.group_button_height)
        # server_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(2))
        # server_btn.setStyleSheet(button_style)
        # self.button_group.addButton(server_btn)

        toolbox_btn = QToolButton()
        toolbox_btn.setText("工具箱")
        toolbox_btn.setCheckable(True)
        toolbox_btn.setFixedWidth(self.group_button_weight)
        toolbox_btn.setFixedHeight(self.group_button_height)
        toolbox_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(2))
        toolbox_btn.setStyleSheet(button_style)
        self.button_group.addButton(toolbox_btn)

        # 将按钮添加到布局（按新顺序）
        button_layout.addWidget(server_btn)
        # button_layout.addWidget(submit_task_btn)
        # button_layout.addWidget(batch_submit_btn)
        # button_layout.addWidget(start_btn)
        button_layout.addWidget(proxy_btn)
        # button_layout.addWidget(server_btn)  # 已移到前面
        button_layout.addWidget(toolbox_btn)

        # 默认选中第一个按钮（服务器按钮）
        server_btn.setChecked(True)

        left_layout.addWidget(button_container)

        main_layout.addWidget(left_container, stretch=70)

        # 3. 右侧导航区域（完全保留原有代码）
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)

        main_layout_size = adapt_component_size([350])  # 减少快捷导航宽度

        nav_widget.setMaximumWidth(main_layout_size[0])
        nav_widget.setMinimumWidth(main_layout_size[0])

        nav_layout.setAlignment(Qt.AlignTop)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        main_layout.addWidget(nav_widget, stretch=30)

        # 4. 创建导航按钮组
        nav_group = QGroupBox("快捷导航")
        nav_group_layout = QVBoxLayout(nav_group)
        nav_group_layout.setContentsMargins(5, 5, 5, 5)
        nav_group_layout.setSpacing(10)
        nav_layout.addWidget(nav_group)

        btn_bg = "#3498db"  # 蓝色背景
        btn_border_radius = 8
        btn_padding1 = 10  # 减少垂直内边距为原来的一半
        btn_padding2 = 30  # 增加水平内边距
        btn_font_size = 24  # 调小字体
        btn_min_height = 40  # 减少最小高度为原来的一半
        btn_hover_bg = "#2980b9"  # 悬停时的深蓝色
        btn_pressed_bg = "#21618c"  # 按下时的更深蓝色

        nav_group_size = adapt_component_size(
            [btn_border_radius, btn_font_size, btn_min_height, btn_padding1, btn_padding2])

        # 5. 创建导航按钮及其点击事件
        btn_style = f"""
            QPushButton {{
                background-color: {btn_bg}; 
                border: 1px solid #ccc; 
                border-radius: {nav_group_size[0]}px;
                padding: {nav_group_size[3]}px {nav_group_size[4]}px;
                font-size: {nav_group_size[1]}px;
                font-weight: bold; 
                color: white;  /* 白色文字在蓝色背景上更清晰 */
                text-align: center;
                min-height: {nav_group_size[2]}px;
            }}
            QPushButton:hover {{ background-color: {btn_hover_bg}; }}
            QPushButton:pressed {{ background-color: {btn_pressed_bg}; }}
            """

        # 数据库按钮
        db_btn = QPushButton("数据库")
        db_btn.setStyleSheet(btn_style)
        db_btn.clicked.connect(self.show_db_window)
        nav_group_layout.addWidget(db_btn)

        web_btn = QPushButton("任务管理")
        web_btn.setStyleSheet(btn_style)
        web_btn.clicked.connect(self.open_web_manager)
        nav_group_layout.addWidget(web_btn)

        # 设置按钮
        setting_btn = QPushButton("设置")
        setting_btn.setStyleSheet(btn_style)
        setting_btn.clicked.connect(self.showSettingsPage)
        nav_group_layout.addWidget(setting_btn)

        # 说明按钮
        help_btn = QPushButton("说明")
        help_btn.setStyleSheet(btn_style)
        help_btn.clicked.connect(self.show_help_window)
        nav_group_layout.addWidget(help_btn)

        # ===== 文件操作按钮组 =====
        file_ops_group = QGroupBox("文件操作")
        file_ops_layout = QVBoxLayout(file_ops_group)
        file_ops_layout.setContentsMargins(5, 5, 5, 5)
        file_ops_layout.setSpacing(10)
        nav_layout.addWidget(file_ops_group)

        if self.project_debug == 0:
            from config.permission_manager import permission_manager
            code_project_mode = permission_manager.load_permissions()

        else:
            code_project_mode = self.code_project_mode_debug
            # 在debug模式下，也将权限设置保存到数据库
            from config.permission_manager import permission_manager
            permission_manager.save_permissions(code_project_mode)

        config_btn1 = QPushButton("系统配置")
        config_btn1.setStyleSheet(btn_style)
        config_btn1.clicked.connect(lambda: self.open_target_folder("配置文件_系统配置", "配置文件"))
        file_ops_layout.addWidget(config_btn1)

        # detect_img_btn = QPushButton("检测图片")
        # detect_img_btn.setStyleSheet(btn_style)
        # detect_img_btn.clicked.connect(self.run_similar_img_detection)
        # file_ops_layout.addWidget(detect_img_btn)

        if "temu" in code_project_mode:
            config_btn2 = QPushButton("工具配置表")
            config_btn2.setStyleSheet(btn_style)
            config_btn2.clicked.connect(lambda: self.open_target_folder("配置文件_工具配置表", "工具配置表"))
            file_ops_layout.addWidget(config_btn2)

            config_btn3 = QPushButton("实拍图配置")
            config_btn3.setStyleSheet(btn_style)
            config_btn3.clicked.connect(lambda: self.open_target_folder("配置文件_实拍图配置", "实拍图配置"))
            file_ops_layout.addWidget(config_btn3)

            # config_btn = QPushButton("配置文件")
            # config_btn.setStyleSheet(button_style)
            # config_btn.clicked.connect(lambda: self.open_target_folder("config", "配置文件"))
            # file_ops_layout.addWidget(config_btn)

        if "caiwu" in code_project_mode:
            # 打开下载表格按钮
            open_downloads_btn = QPushButton("结算导出")
            open_downloads_btn.setStyleSheet(btn_style)
            open_downloads_btn.clicked.connect(lambda: self.open_target_folder("配置文件_结算导出", "下载表格文件夹"))
            file_ops_layout.addWidget(open_downloads_btn)

            # 打开成本按钮
            open_cost_btn = QPushButton("成本配置")
            open_cost_btn.setStyleSheet(btn_style)
            open_cost_btn.clicked.connect(lambda: self.open_target_folder("配置文件_成本", "成本配置"))
            file_ops_layout.addWidget(open_cost_btn)

            open_result_btn = QPushButton("财务汇总")
            open_result_btn.setStyleSheet(btn_style)
            open_result_btn.clicked.connect(lambda: self.open_target_folder("配置文件_财务汇总", "财务汇总"))
            file_ops_layout.addWidget(open_result_btn)

        # ==================================

        nav_layout.addStretch()

    def showEvent(self, event):
        """窗口首次显示时自动居中"""
        if not hasattr(self, '_has_centered'):
            self.center()
            self._has_centered = True
        super().showEvent(event)

    def center(self):
        screen_geo = QApplication.primaryScreen().availableGeometry()
        # 使用当前实际尺寸（此时已 layout 完成）
        window_width = self.width()
        window_height = self.height()
        x = screen_geo.x() + (screen_geo.width() - window_width) // 2
        y = screen_geo.y() + (screen_geo.height() - window_height) // 2
        self.move(x, y)

    def show_db_window(self):
        # 检查窗口是否已存在且可见
        if self.db_window is not None and self.db_window.isVisible():
            self.db_window.activateWindow()
            self.db_window.raise_()
            return
        
        # 如果窗口对象存在但不可见，先清理资源
        if self.db_window is not None:
            try:
                self.db_window.close()
                self.db_window.deleteLater()
            except Exception as e:
                logger.warning(f"清理数据库窗口时出错: {e}")
            finally:
                self.db_window = None
        
        try:
            # 核心修改：用根目录替代 gui/ 目录
            root_dir = get_app_root_dir()
            DB_PATH = os.path.join(root_dir, "配置文件_系统配置", "db_config.json")

            # 获取用户权限
            if self.project_debug == 0:
                from config.permission_manager import permission_manager
                code_project_mode = permission_manager.load_permissions()
            else:
                code_project_mode = self.code_project_mode_debug

            # 构建分页配置列表
            tab_configs = []

            # 任务管理 - 所有情况下都是第一个选项卡
            tab_configs.append(
                create_tab_config(
                    tab_name="任务管理",
                    table_name="task",
                    columns_to_display=["id", "task_name", "status", "func_name", "task_group", "msg", "remarks", "task_id", "ip",
                                        "create_time", "update_time"],
                    column_aliases={
                        "id": "ID",
                        "task_name": "任务名称",
                        "status": "状态",
                        "func_name": "函数名称",
                        "task_group": "任务组",
                        "msg": "信息",
                        "remarks": "备注",
                        "log": "日志",
                        "task_id": "任务ID",
                        "ip": "代理ip",
                        "create_time": "创建时间",
                        "update_time": "更新时间"
                    },
                    column_width_config={
                        "id": ("Fixed", 60),
                        "task_name": ("Fixed", 200),
                        "status": ("Fixed", 80),
                        "func_name": ("Fixed", 200),
                        "task_group": ("Fixed", 150),
                        "msg": ("Fixed", 200),
                        "remarks": ("Fixed", 200),
                        "task_id": ("Fixed", 200),
                        "ip": ("Fixed", 120),
                        "create_time": ("Fixed", 150),
                        "update_time": ("Fixed", 150)
                    },
                    context_menu_actions=[
                        {"修改状态": lambda ids: viewer.modify_task_status(ids)},
                        {"删除任务": lambda ids: viewer.delete_task_rows(ids)}
                    ]
                )
            )

            # 店铺管理 - 只在temu或caiwu权限时显示
            if "temu" in code_project_mode or "caiwu" in code_project_mode:
                tab_configs.append(
                    create_tab_config(
                        tab_name="店铺管理",
                        table_name="shops",
                        columns_to_display=["id", "shop_name", "shop_abbr", "phone", "password",
                                            "connect_status", "create_time", "update_time", "headers", "cookies"],
                        column_width_config={
                            "id": ("Fixed", 60),
                            "shop_name": ("Fixed", 150),
                            "shop_abbr": ("Fixed", 100),
                            "phone": ("Fixed", 120),
                            "password": ("Fixed", 120),
                            "connect_status": ("Fixed", 100),
                            "create_time": ("Fixed", 150),
                            "update_time": ("Fixed", 150),
                            "headers": ("Fixed", 200),
                            "cookies": ("Fixed", 200)
                        },
                        context_menu_actions=[
                            {"修改手机号": lambda ids: viewer.modify_field("shops", "phone", "手机号", ids)},
                            {"修改密码": lambda ids: viewer.modify_field("shops", "password", "密码", ids)},
                            {"清空认证": lambda ids: viewer.clear_auth("shops", ids)},
                            {"清空实拍图SPU记录": lambda ids: viewer.clear_shop_upload_pic_spu_record(ids)},
                            {"删除选中行": lambda ids: viewer.delete_rows("shops", ids)}
                        ]
                    )
                )

            # 虎扑数据库分页 - 只在spider权限时显示
            if "spider" in code_project_mode:
                HUPU_DB_CONFIG_PATH = os.path.join(root_dir, "配置文件_系统配置", "hupu_db_config.json")
                HUPU_DB_PATH = os.path.join(root_dir, "配置文件_系统配置", "hupu.db")

                # 如果配置文件不存在，创建它
                import json
                if not os.path.exists(HUPU_DB_CONFIG_PATH):
                    with open(HUPU_DB_CONFIG_PATH, "w", encoding="utf-8") as f:
                        json.dump({"db_path": HUPU_DB_PATH}, f)

                # 第一个：AI分析结果页（原订单列表）
                tab_configs.append(
                    create_tab_config(
                        tab_name="AI分析结果",
                        table_name="ai_analysis",
                        db_path=HUPU_DB_CONFIG_PATH,
                        columns_to_display=["id", "task_name", "status", "msg", "remarks", "task_id", "type", "ai_sumup"],
                        column_aliases={
                            "id": "ID",
                            "task_name": "任务名称",
                            "status": "状态",
                            "msg": "信息",
                            "remarks": "备注",
                            "task_id": "任务ID",
                            "type": "类型",
                            "ai_sumup": "AI总结"
                        },
                        column_width_config={
                            "id": ("Fixed", 60),
                            "task_name": ("Fixed", 150),
                            "status": ("Fixed", 80),
                            "msg": ("Fixed", 200),
                            "remarks": ("Fixed", 120),
                            "task_id": ("Fixed", 200),
                            "type": ("Fixed", 80),
                            "ai_sumup": ("Fixed", 200)
                        },
                        context_menu_actions=[
                            {"删除选中行": lambda ids: viewer.delete_rows("ai_analysis", ids)}
                        ]
                    )
                )

                # 第二个：帖子列表
                tab_configs.append(
                    create_tab_config(
                        tab_name="帖子列表",
                        table_name="hupu_post_list",
                        db_path=HUPU_DB_CONFIG_PATH,
                        columns_to_display=["id", "huputitle", "hupu_zone", "posturl", "replies",
                                            "tuijian_count", "fatietime", "addtime", "liangping_count", "task_id"],
                        column_aliases={
                            "id": "ID",
                            "huputitle": "虎扑标题",
                            "hupu_zone": "虎扑分区",
                            "posturl": "帖子URL",
                            "replies": "回复数",
                            "tuijian_count": "推荐数",
                            "fatietime": "发帖时间",
                            "addtime": "添加时间",
                            "liangping_count": "亮评数",
                            "task_id": "任务ID"
                        },
                        column_width_config={
                            "id": ("Fixed", 60),
                            "huputitle": ("Fixed", 200),
                            "hupu_zone": ("Fixed", 100),
                            "posturl": ("Fixed", 250),
                            "replies": ("Fixed", 80),
                            "tuijian_count": ("Fixed", 80),
                            "fatietime": ("Fixed", 150),
                            "addtime": ("Fixed", 150),
                            "liangping_count": ("Fixed", 80)
                        },
                        context_menu_actions=[
                            {"导出": lambda ids: viewer.export_selected_rows("hupu_post_list", ids)},
                            {"删除选中行": lambda ids: viewer.delete_rows("hupu_post_list", ids)}
                        ]
                    )
                )

                # 第三个：帖子详情
                tab_configs.append(
                    create_tab_config(
                        tab_name="帖子详情",
                        table_name="hupu_detail_list",
                        db_path=HUPU_DB_CONFIG_PATH,
                        columns_to_display=["id", "fabucontent", "nickname", "replycontent", "floor",
                                            "ipaddress", "posttitle", "like_count", "posturl", "replytime",
                                            "addtime", "task_id", "reply_count"],
                        column_aliases={
                            "id": "ID",
                            "fabucontent": "发布内容",
                            "nickname": "昵称",
                            "replycontent": "回复内容",
                            "floor": "楼层",
                            "ipaddress": "IP地址",
                            "posttitle": "帖子标题",
                            "like_count": "点赞数",
                            "posturl": "帖子URL",
                            "replytime": "回复时间",
                            "addtime": "添加时间",
                            "task_id": "任务ID",
                            "reply_count": "回复数"
                        },
                        column_width_config={
                            "id": ("Fixed", 60),
                            "fabucontent": ("Fixed", 200),
                            "nickname": ("Fixed", 100),
                            "replycontent": ("Fixed", 200),
                            "floor": ("Fixed", 60),
                            "ipaddress": ("Fixed", 120),
                            "posttitle": ("Fixed", 180),
                            "like_count": ("Fixed", 80),
                            "posturl": ("Fixed", 200),
                            "replytime": ("Fixed", 150),
                            "addtime": ("Fixed", 150),
                            "reply_count": ("Fixed", 80)
                        },
                        context_menu_actions=[
                            {"导出": lambda ids: viewer.export_selected_rows("hupu_detail_list", ids)},
                            {"删除选中行": lambda ids: viewer.delete_rows("hupu_detail_list", ids)}
                        ]
                    )
                )

                # 第四个：虎扑评分
                tab_configs.append(
                    create_tab_config(
                        tab_name="虎扑评分",
                        table_name="hupu_score_list",
                        db_path=HUPU_DB_CONFIG_PATH,
                        columns_to_display=["id", "name", "time", "location", "comment",
                                            "reply_comment", "like_count", "score", "score_title",
                                            "addtime", "task_id", "scoreurl"],
                        column_aliases={
                            "id": "ID",
                            "name": "名称",
                            "time": "时间",
                            "location": "位置",
                            "comment": "评论",
                            "reply_comment": "回复评论",
                            "like_count": "点赞数",
                            "score": "评分",
                            "score_title": "评分标题",
                            "addtime": "添加时间",
                            "task_id": "任务ID",
                            "scoreurl": "评分URL"
                        },
                        column_width_config={
                            "id": ("Fixed", 60),
                            "name": ("Fixed", 120),
                            "time": ("Fixed", 150),
                            "location": ("Fixed", 100),
                            "comment": ("Fixed", 200),
                            "reply_comment": ("Fixed", 200),
                            "like_count": ("Fixed", 80),
                            "score": ("Fixed", 60),
                            "score_title": ("Fixed", 150),
                            "addtime": ("Fixed", 150),
                            "scoreurl": ("Fixed", 200)
                        },
                        context_menu_actions=[
                            {"导出": lambda ids: viewer.export_selected_rows("hupu_score_list", ids)},
                            {"删除选中行": lambda ids: viewer.delete_rows("hupu_score_list", ids)}
                        ]
                    )
                )

            viewer = DbTableViewer(DB_PATH, tab_configs)

            # 保存窗口引用，防止被垃圾回收
            self.db_window = viewer

            # 添加窗口关闭事件处理，当窗口关闭时将引用设为None
            self.db_window.closeEvent = lambda e: self.on_db_window_closed(e)

            viewer.show()

        except Exception as e:
            error_msg = f"创建数据库窗口失败: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "错误", error_msg)

    def on_db_window_closed(self, event):
        """处理数据库窗口关闭事件"""
        self.db_window = None
        event.accept()
        
    def on_settings_window_closed(self, event):
        """处理设置窗口关闭事件"""
        self.settings_window = None
        event.accept()
        
    def on_help_window_closed(self, event):
        """处理帮助窗口关闭事件"""
        self.help_window = None
        event.accept()

    def open_web_manager(self):
        """
        打开电脑默认浏览器访问 localhost:1234
        :return: bool - 是否成功打开浏览器
        """
        from config.common_config import config_manager
        from lite_modules.web_utils import open_url_in_browser_core

        # 从数据库读取配置
        external_ip = config_manager.get_or_set_config("ServerPage_external_ip", "localhost")
        port = config_manager.get_or_set_config("ServerPage_port", "8888")
        token = config_manager.get_or_set_config("ServerPage_token", "")

        if external_ip.strip() == "":
            # 获取本机IP
            external_ip = "0.0.0.0"

        url = f"http://{external_ip}:{port}?token={token}"
        return open_url_in_browser_core(url)
    
    def open_url_in_browser_core(self, url):
        """
        通用的核心打开网页函数（复用lite_modules中的核心函数）
        :param url: 要打开的URL
        :return: bool - 是否成功打开浏览器
        """
        from lite_modules.web_utils import open_url_in_browser_core
        return open_url_in_browser_core(url)

    def showSettingsPage(self):
        # 检查窗口是否已存在且可见
        if hasattr(self, 'settings_window') and self.settings_window is not None and self.settings_window.isVisible():
            self.settings_window.activateWindow()
            self.settings_window.raise_()
            return
        
        # 如果窗口对象存在但不可见，先清理资源
        if hasattr(self, 'settings_window') and self.settings_window is not None:
            try:
                self.settings_window.close()
                self.settings_window.deleteLater()
            except Exception as e:
                logger.warning(f"清理设置窗口时出错: {e}")
            finally:
                self.settings_window = None

        # 创建并显示新窗口（改为无父窗口的独立窗口）
        self.settings_window = SettingWindow(parent=self)
        # 添加窗口关闭事件处理
        self.settings_window.closeEvent = lambda e: self.on_settings_window_closed(e)
        self.settings_window.show()

    def show_help_window(self):
        try:
            # 检查窗口是否已存在且可见
            if hasattr(self, 'help_window') and self.help_window is not None and self.help_window.isVisible():
                self.help_window.activateWindow()
                self.help_window.raise_()
                return
            
            # 如果窗口对象存在但不可见，先清理资源
            if hasattr(self, 'help_window') and self.help_window is not None:
                try:
                    self.help_window.close()
                    self.help_window.deleteLater()
                except Exception as e:
                    logger.warning(f"清理帮助窗口时出错: {e}")
                finally:
                    self.help_window = None
            
            # 创建并显示新窗口（改为无父窗口的独立窗口）
            self.help_window = HelpWindow()
            # 添加窗口关闭事件处理
            self.help_window.closeEvent = lambda e: self.on_help_window_closed(e)
            self.help_window.show()
        except Exception as e:
            error_msg = f"创建帮助窗口失败: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(self, "错误", error_msg)

    def open_folder_in_explorer(self, folder_path: str, description: str = "文件夹"):
        """
        修复版：使用os.startfile()或subprocess在资源管理器中打开文件夹
        """
        path_obj = Path(folder_path)

        # 1. 检查并创建路径
        if not path_obj.exists():
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
                logger.info(f"路径 '{folder_path}' 不存在，已自动创建。")
            except OSError as e:
                QMessageBox.critical(self, "权限错误",
                                     f"无法创建{description}路径 '{folder_path}'。\n"
                                     f"错误: {e}\n\n"
                                     f"请检查：\n"
                                     f"1. Python是否有D盘写入权限\n"
                                     f"2. 是否以管理员身份运行程序\n"
                                     f"3. 路径是否被杀毒软件阻止")
                return

        if not path_obj.is_dir():
            QMessageBox.warning(self, "警告", f"路径 '{folder_path}' 不是一个有效的文件夹。")
            return

        # 2. 使用跨平台方式打开文件夹
        try:
            if platform.system() == "Windows":
                # Windows: 使用 os.startfile() 最可靠
                os.startfile(str(path_obj))
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(path_obj)], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", str(path_obj)], check=True)

        except Exception as e:
            # 如果打开失败，提供更具体的错误信息
            error_msg = f"打开{description}失败。\n路径: {folder_path}\n错误: {e}"

            # 检查是否为权限问题
            if "权限" in str(e) or "Permission" in str(e):
                error_msg += "\n\n建议：以管理员身份运行此程序"

            QMessageBox.critical(self, "错误", error_msg)

    def open_target_folder(self, folder_name: str, description: str):
        """
        :param folder_name: 文件夹名称（如 "download"、"配置文件_成本"、"配置文件_财务汇总"）
        :param description: 文件夹描述（用于提示文案，如 "下载表格文件夹"、"成本文件夹"）
        """
        root_dir = get_app_root_dir()
        target_path = os.path.join(root_dir, folder_name)
        self.open_folder_in_explorer(target_path, description)

    def run_similar_img_detection(self):
        """运行图片相似度检测（多进程）"""
        try:
            # 禁用按钮，防止重复点击
            sender = self.sender()
            if sender:
                sender.setEnabled(False)
                sender.setText("检测中...")
            
            # 获取当前脚本目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            
            # 使用 subprocess.Popen 替代 multiprocessing.Process
            # 这样可以确保子进程使用正确的 Python 解释器和环境
            import subprocess
            import sys
            import threading
            from queue import Queue, Empty
            
            # 获取 Python 解释器路径
            python_exe = sys.executable
            
            # 构建 similar_pic.py 的完整路径
            similar_pic_path = os.path.join(project_root, "similar_pic.py")
            
            # 设置子进程环境变量
            env = os.environ.copy()
            
            # 如果是打包后的环境，添加必要的路径到环境变量
            if getattr(sys, 'frozen', False):
                # 打包后的环境
                base_path = os.path.dirname(sys.executable)
                # 添加浏览器文件路径到环境变量
                env['PATH'] = base_path + os.pathsep + env.get('PATH', '')
            
            # 启动子进程，不重定向输出，直接显示在控制台
            process = subprocess.Popen(
                [python_exe, similar_pic_path],
                cwd=project_root,
                env=env,
                # 不使用 PIPE，让输出直接显示在控制台
                creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == 'Windows' else 0
            )
            
            # 不使用 wait()，避免阻塞主界面
            # 进程会在后台独立运行
            
            # 3秒后恢复按钮状态
            QTimer.singleShot(3000, lambda: self._restore_detect_button(sender))
            
            QMessageBox.information(
                self,
                "提示",
                "图片相似度检测已在后台启动，\n请查看新打开的控制台窗口获取检测结果。",
                QMessageBox.Ok
            )
            
        except Exception as e:
            logger.error(f"启动图片检测失败：{str(e)}", exc_info=True)
            QMessageBox.critical(
                self,
                "错误",
                f"启动图片检测失败：{str(e)}",
                QMessageBox.Ok
            )
            # 恢复按钮状态
            if sender:
                sender.setEnabled(True)
                sender.setText("检测图片")
    
    def _restore_detect_button(self, button):
        """恢复检测按钮状态"""
        if button:
            button.setEnabled(True)
            button.setText("检测图片")

    def handle_expire(self):
        """主线程：处理“到期”信号（先清理后台任务，再弹窗提示，保留主界面）"""
        try:
            logger.info("检测到卡密到期，正在退出后台任务...")

            # 停止所有后台任务（子进程、子线程等）
            stop_main_api_process()
            stop_cycle_thread()

            if 'MAIN_TASK_MANAGER' in globals():
                MAIN_TASK_MANAGER.stop()
                logger.info("任务管理器已停止")

            # 可选：禁用主窗口交互（防止用户继续操作）
            self.setEnabled(False)  # 假设 self 是主窗口（QMainWindow 或 QWidget）

            # 弹出模态提示（阻塞，必须点击确定）
            QMessageBox.critical(
                self,
                "版本到期",
                "您的卡密已到期，程序将停止运行。",
                QMessageBox.Ok
            )

            # 注意：这里不再调用 app.quit()！
            # 主界面仍然存在，但已禁用（或可选择隐藏某些控件）
            logger.info("后台任务已退出")

            # 如果你希望用户点击“确定”后自动退出，可以在这里加：
            QApplication.instance().quit()
            # 但根据你的需求，目前是“保留主界面”，所以不退出

        except Exception as e:
            logger.error(f"到期处理异常：{str(e)}", exc_info=True)
            # 即使出错，也至少弹窗提示
            QMessageBox.critical(
                self,
                "错误",
                f"程序到期处理失败：{str(e)}\n即将退出。",
                QMessageBox.Ok
            )
            # 异常情况下可选择强制退出
            QApplication.instance().quit()