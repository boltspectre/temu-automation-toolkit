# ToolsPage.py

# 新增：位置测试相关依赖
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QTextOption, QFont
from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QGroupBox, QTabWidget,
                             QWidget, QLabel, QPushButton, QTextEdit,
                             QFrame, QApplication, QComboBox, QLineEdit, QCheckBox,
                             QHBoxLayout, QMessageBox)

from gui.change_upload_pic_index import ConfigWindow
from config.common_config import config_manager, encryptor
from config.kami_config import kami_config
from config.py_config import config_value
from config.permission_manager import permission_manager
from gui.CustomFolderBrowser import CustomFileManager
from gui.GoRun import ZiyanWindow
from gui.RequestSettings import RequestsSettings
from gui.RequestsTool import RequestsTool


class ToolsPage(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ikun联盟 - 工具箱")
        self.setWindowIcon(QIcon('gui/img/favicon.ico'))
        self.resize(1050, 700)
        # 移除 QEventLoop 相关代码，避免 Qt 初始化冲突

        # 使用数据库配置管理器替代配置加载器
        self.config = None

        self.ziyan_is_started = False

        login_data = encryptor.load_login_data()
        self.ddos = "False"
        if login_data:
            self.ddos = login_data.get('ddos')

        self.permissions = permission_manager.load_permissions()
        self.temu = "True" if "temu" in self.permissions else "False"

        self.initUI()

    def initUI(self):
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # 创建选项卡控件
        self.tab_widget = QTabWidget()

        # 添加所有选项卡（新增位置测试分页）
        self.createSentTab()
        self.createRequestSettings()
        # 只有temu权限为True时才添加实拍图标注测试选项卡
        if self.temu == "True":
            self.createPositionTestTab()  # 新增：位置测试分页
        self.createAttackTab()
        self.createHelpTab()

        # 将选项卡直接添加到布局
        layout.addWidget(self.tab_widget)

        # 解密并获取登录信息
        if self.ddos == "True":
            pass
        else:
            self.ziyan_start_button.setEnabled(False)

        # 连接所有控件的信号
        self.connect_config_signals()

        # 从配置文件加载设置到UI
        self.setup_ui()
        
        # 延迟加载HTTP请求配置，确保所有UI组件都已创建
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.load_http_request_config)

    def connect_config_signals(self):
        """连接所有需要保存配置的控件信号"""
        # 自研混合压测模型设置
        self.ziyan_target_url.textChanged.connect(
            lambda: self.update_config('ziyan_target_url', self.ziyan_target_url.text()))
        self.ziyan_mode_combo.currentIndexChanged.connect(
            lambda: self.update_config('ziyan_mode_combo', str(self.ziyan_mode_combo.currentIndex())))
        self.ziyan_task_count.textChanged.connect(
            lambda: self.update_config('ziyan_task_count', self.ziyan_task_count.text()))
        self.ziyan_time.textChanged.connect(
            lambda: self.update_config('ziyan_time', self.ziyan_time.text()))
        self.ziyan_all_time.stateChanged.connect(
            lambda: self.update_config('ziyan_all_time', str(self.ziyan_all_time.isChecked())))
        self.ziyan_console_mode.stateChanged.connect(
            lambda: self.update_config('ziyan_console_mode', str(self.ziyan_console_mode.isChecked())))
        self.ziyan_cloud_proxy.stateChanged.connect(
            lambda: self.update_config('ziyan_cloud_proxy', str(self.ziyan_cloud_proxy.isChecked())))
        self.ziyan_local_proxy.stateChanged.connect(
            lambda: self.update_config('ziyan_local_proxy', str(self.ziyan_local_proxy.isChecked())))
        self.ziyan_process_guard.stateChanged.connect(
            lambda: self.update_config('ziyan_process_guard', str(self.ziyan_process_guard.isChecked())))
        self.ziyan_enable_proxy.stateChanged.connect(
            lambda: self.update_config('ziyan_enable_proxy', str(self.ziyan_enable_proxy.isChecked())))
        self.ziyan_auto_workers.stateChanged.connect(
            lambda: self.update_config('ziyan_auto_workers', str(self.ziyan_auto_workers.isChecked())))
        self.ziyan_connection_mode.currentIndexChanged.connect(
            lambda: self.update_config('ziyan_connection_mode', str(self.ziyan_connection_mode.currentIndex())))

    def update_config(self, key, value):
        """更新配置并保存"""
        config_manager.upsert_config(f"ToolsPage_{key}", str(value))

    def setup_ui(self):
        """从配置文件加载设置到UI"""
        # 自研混合压测模型设置
        self.ziyan_target_url.setText(config_manager.get_or_set_config("ToolsPage_ziyan_target_url", ""))
        mode_index = int(config_manager.get_or_set_config("ToolsPage_ziyan_mode_combo", "0"))
        self.ziyan_mode_combo.setCurrentIndex(mode_index)
        self.ziyan_task_count.setText(config_manager.get_or_set_config("ToolsPage_ziyan_task_count", ""))
        self.ziyan_time.setText(config_manager.get_or_set_config("ToolsPage_ziyan_time", ""))
        all_time = config_manager.get_or_set_config("ToolsPage_ziyan_all_time", "False")
        self.ziyan_all_time.setChecked(all_time.lower() == "true")
        console_mode = config_manager.get_or_set_config("ToolsPage_ziyan_console_mode", "False")
        self.ziyan_console_mode.setChecked(console_mode.lower() == "true")
        cloud_proxy = config_manager.get_or_set_config("ToolsPage_ziyan_cloud_proxy", "False")
        self.ziyan_cloud_proxy.setChecked(cloud_proxy.lower() == "true")
        local_proxy = config_manager.get_or_set_config("ToolsPage_ziyan_local_proxy", "False")
        self.ziyan_local_proxy.setChecked(local_proxy.lower() == "true")
        process_guard = config_manager.get_or_set_config("ToolsPage_ziyan_process_guard", "False")
        self.ziyan_process_guard.setChecked(process_guard.lower() == "true")
        enable_proxy = config_manager.get_or_set_config("ToolsPage_ziyan_enable_proxy", "False")
        self.ziyan_enable_proxy.setChecked(enable_proxy.lower() == "true")
        auto_workers = config_manager.get_or_set_config("ToolsPage_ziyan_auto_workers", "False")
        self.ziyan_auto_workers.setChecked(auto_workers.lower() == "true")
        connection_mode_index = int(config_manager.get_or_set_config("ToolsPage_ziyan_connection_mode", "0"))
        self.ziyan_connection_mode.setCurrentIndex(connection_mode_index)

        saved_version = config_manager.get_or_set_config("ToolsPage_ziyan_selected_version")
        if saved_version:
            # 查找版本在下拉框中的索引
            index = self.ziyan_name_combo.findText(saved_version)
            if index >= 0:
                self.ziyan_name_combo.setCurrentIndex(index)

    def load_http_request_config(self):
        """加载HTTP请求配置到两个选项卡"""
        try:
            # 加载基础请求配置到HTTP请求选项卡
            url = config_manager.get_or_set_config("http_request_url", "")
            params = config_manager.get_or_set_config("http_request_params", "")
            method = config_manager.get_or_set_config("http_request_method", "GET")
            
            if hasattr(self, 'requests_tool'):
                # 检查必要的UI属性是否存在
                required_attrs = ['url_input', 'method_combo', 'params_input']
                missing_attrs = [attr for attr in required_attrs if not hasattr(self.requests_tool, attr)]
                
                if missing_attrs:
                    print(f"缺少UI属性: {missing_attrs}")
                    return
                
                # 设置值
                self.requests_tool.url_input.setText(url)
                self.requests_tool.params_input.setPlainText(params)
                
                # 设置请求方法
                index = self.requests_tool.method_combo.findText(method)
                if index >= 0:
                    self.requests_tool.method_combo.setCurrentIndex(index)
            
            # 请求设置选项卡的配置由RequestsSettings自行加载
            # 在RequestsSettings的__init__方法中已经调用了load_config方法
            
        except Exception as e:
            print(f"加载HTTP请求配置失败: {str(e)}")

    def createSentTab(self):
        """HTTP请求选项卡"""
        self.requests_tool = RequestsTool(parent=self)
        
        # 直接将RequestsTool添加到选项卡中
        self.tab_widget.addTab(self.requests_tool, "HTTP请求")

    def createRequestSettings(self):
        """实拍图位置测试（原重复定义的方法已修正）"""
        self.settings_widget = RequestsSettings()
        # 创建容器并添加组件
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.settings_widget)
        self.tab_widget.addTab(container, "请求设置")

    def createPositionTestTab(self):
        """修改为：复用ConfigWindow组件，不再重复写UI"""
        # 1. 创建标签页容器
        position_widget = QWidget()
        main_layout = QVBoxLayout(position_widget)

        # 2. 实例化ConfigWindow（复用已有逻辑）
        self.config_window = ConfigWindow(parent=position_widget)  # 传递父组件

        # 3. 将ConfigWindow添加到标签页布局
        main_layout.addWidget(self.config_window)

        # 4. 添加到选项卡
        self.tab_widget.addTab(position_widget, "实拍图标注测试")

    def createAttackTab(self):
        """Attack选项卡"""
        settings_widget = QWidget()
        main_layout = QVBoxLayout(settings_widget)

        ziyan_groupbox = self.setup_ziyan_groupbox()
        main_layout.addWidget(ziyan_groupbox)

        main_layout.addStretch()

        settings_widget.setLayout(main_layout)
        self.tab_widget.addTab(settings_widget, "压测模块")

    def setup_ziyan_groupbox(self):
        start_groupbox = QGroupBox("自研混合压力测试模型")
        layout = QHBoxLayout()

        # 左侧启动按钮区域
        button_layout = QVBoxLayout()
        self.ziyan_start_button = QPushButton("启动")
        self.ziyan_start_button.setStyleSheet("""
                    QPushButton {
                        font-size: 25px;
                    }
                """)
        self.ziyan_start_button.setIconSize(QSize(32, 32))
        self.ziyan_start_button.clicked.connect(self.start_ziyan_attack)
        self.ziyan_start_button.setIcon(QIcon("gui/img/qidong.png"))
        button_layout.addWidget(self.ziyan_start_button)

        if self.ddos != "True":
            no_permission_label = QLabel("无权限")
            no_permission_label.setStyleSheet("color: red; font-size: 26px;")
            no_permission_label.setAlignment(Qt.AlignCenter)
            button_layout.addWidget(no_permission_label)
            self.ziyan_start_button.setEnabled(False)

        layout.addLayout(button_layout)

        # 右侧控件区域
        right_layout = QVBoxLayout()

        # 第一行控件
        row1_layout = QHBoxLayout()
        row1_layout.addWidget(QLabel("目标URL:"))
        self.ziyan_target_url = QLineEdit()
        self.ziyan_target_url.setPlaceholderText("请填写完整协议+域名 http://example.com")
        self.ziyan_target_url.setFixedWidth(480)
        row1_layout.addWidget(self.ziyan_target_url)

        row1_layout.addWidget(QLabel("压测模式:"))
        self.ziyan_mode_combo = QComboBox()
        self.ziyan_mode_combo.addItems(
            ["混合模式", "全随机模式", "洪水模式", "慢连接模式", "异步模式"])
        self.ziyan_mode_combo.setFixedWidth(180)
        row1_layout.addWidget(self.ziyan_mode_combo)

        row1_layout.addStretch()
        right_layout.addLayout(row1_layout)

        # 第二行控件
        row2_layout = QHBoxLayout()

        row2_layout.addWidget(QLabel("并发数:"))
        self.ziyan_task_count = QLineEdit()
        self.ziyan_task_count.setPlaceholderText("20000")
        self.ziyan_task_count.setFixedWidth(100)
        row2_layout.addWidget(self.ziyan_task_count)

        row2_layout.addWidget(QLabel("持续时间:"))
        self.ziyan_time = QLineEdit()
        self.ziyan_time.setPlaceholderText("单位/秒")
        self.ziyan_time.setFixedWidth(120)
        row2_layout.addWidget(self.ziyan_time)

        self.ziyan_all_time = QCheckBox("无限时间")
        row2_layout.addWidget(self.ziyan_all_time)

        row2_layout.addWidget(QLabel("版本:"))
        self.ziyan_name_combo = QComboBox()

        # 扫描gui/Go/目录下的文件并按规则排序
        try:
            from main import ROOT_DIR
            go_dir = Path(ROOT_DIR) / "gui" / "Go"
        except ImportError:
            # 如果无法导入全局路径，则使用相对路径作为后备
            go_dir = Path("gui/Go")

        files = []
        if go_dir.exists():
            files = [f.name for f in go_dir.iterdir() if f.is_file()]

        # 排序规则：
        # 1. 带"ziyan"且带".exe"的排在最前面
        # 2. 带"ziyan"但不带".exe"的排在中间
        # 3. 不带"ziyan"的排在最后面
        sorted_files = sorted(files, key=lambda x: (
            0 if "ziyan" in x.lower() and x.lower().endswith(".exe") else
            1 if "ziyan" in x.lower() else
            2,
            x.lower()
        ))

        # 添加到下拉框
        self.ziyan_name_combo.addItems(sorted_files)
        # 固定添加“打开文件夹+”到最后一位（不再用分隔线，避免刷新后错位）
        self.ziyan_name_combo.addItem("打开文件夹+")

        self.ziyan_name_combo.setFixedWidth(230)
        row2_layout.addWidget(self.ziyan_name_combo)

        self.ziyan_name_combo.currentIndexChanged.connect(self.on_ziyan_combo_changed)

        row2_layout.addStretch()
        right_layout.addLayout(row2_layout)

        row3_layout = QHBoxLayout()
        self.ziyan_console_mode = QCheckBox("控制台模式")
        row3_layout.addWidget(self.ziyan_console_mode)

        self.ziyan_enable_proxy = QCheckBox("启用代理服务")
        row3_layout.addWidget(self.ziyan_enable_proxy)

        self.ziyan_local_proxy = QCheckBox("启用本地代理ip")
        row3_layout.addWidget(self.ziyan_local_proxy)

        self.ziyan_cloud_proxy = QCheckBox("官方云端代理ip")
        row3_layout.addWidget(self.ziyan_cloud_proxy)

        row3_layout.addStretch()
        right_layout.addLayout(row3_layout)

        row4_layout = QHBoxLayout()
        self.ziyan_auto_workers = QCheckBox("低伤害模式")
        row4_layout.addWidget(self.ziyan_auto_workers)

        row4_layout.addWidget(QLabel("连接模式:"))
        self.ziyan_connection_mode = QComboBox()
        self.ziyan_connection_mode.addItems(
            ["自动", "普通模式", "长连接模式"])
        self.ziyan_connection_mode.setFixedWidth(150)
        row4_layout.addWidget(self.ziyan_connection_mode)

        self.ziyan_process_guard = QCheckBox("进程守护")
        row4_layout.addWidget(self.ziyan_process_guard)

        row4_layout.addStretch()
        right_layout.addLayout(row4_layout)

        layout.addLayout(right_layout)
        start_groupbox.setLayout(layout)
        return start_groupbox

    # 实现槽函数
    def on_ziyan_combo_changed(self, index):
        selected_text = self.ziyan_name_combo.currentText()
        # 记录当前选中的有效版本（用于后续重置，排除"打开文件夹+"）
        last_valid_version = config_manager.get_or_set_config("ToolsPage_ziyan_selected_version")

        if selected_text == "打开文件夹+":
            try:
                from main import ROOT_DIR
                target_dir = Path(ROOT_DIR) / "gui" / "Go"
            except ImportError:
                # 如果无法导入全局路径，则使用相对路径作为后备
                target_dir = Path("gui/Go")

            # 打开文件管理器
            self.file_manager = CustomFileManager(
                folder_path=target_dir,
                title="文件管理器",
            )
            self.file_manager.file_changed_signal.connect(self.update_ziyan_combo)
            self.file_manager.show()

            # 核心优化：不选中"打开文件夹+"，立即重置选中项
            if last_valid_version:
                # 优先恢复之前保存的有效版本
                valid_index = self.ziyan_name_combo.findText(last_valid_version)
                if valid_index >= 0:
                    self.ziyan_name_combo.setCurrentIndex(valid_index)
                else:
                    # 保存的版本不存在，选中第0项（第一个.exe文件）
                    if self.ziyan_name_combo.count() > 1:  # 至少有1个.exe文件+1个"打开文件夹+"
                        self.ziyan_name_combo.setCurrentIndex(0)
            else:
                # 无保存版本，默认选中第0项（第一个.exe文件）
                if self.ziyan_name_combo.count() > 1:
                    self.ziyan_name_combo.setCurrentIndex(0)
        else:
            # 选中的是有效.exe文件，更新配置
            self.update_config('ziyan_selected_version', selected_text)

    def update_ziyan_combo(self):
        """文件变动后，重新读取gui/Go文件夹，更新下拉框选项"""
        try:
            from main import ROOT_DIR
            target_dir = Path(ROOT_DIR) / "gui" / "Go"
        except ImportError:
            # 如果无法导入全局路径，则使用相对路径作为后备
            target_dir = Path("gui/Go")

        # 记录刷新前保存的有效版本（用于后续恢复）
        saved_version = config_manager.get_or_set_config("ToolsPage_ziyan_selected_version")

        # 1. 清空下拉框
        self.ziyan_name_combo.clear()

        # 2. 重新读取并添加.exe文件（按规则排序）
        try:
            files = [f.name for f in target_dir.iterdir() if f.is_file() and f.suffix.lower() == ".exe"]
            sorted_files = sorted(files, key=lambda x: (
                0 if "ziyan" in x.lower() else 1,
                x.lower()
            ))
            self.ziyan_name_combo.addItems(sorted_files)
            print(f"下拉框已更新，共{len(sorted_files)}个.exe文件")
        except FileNotFoundError:
            self.ziyan_name_combo.addItem("⚠️ gui/Go文件夹不存在")
            print("错误：未找到gui/Go文件夹")
        except PermissionError:
            self.ziyan_name_combo.addItem("⚠️ 无文件夹访问权限")
            print("错误：无gui/Go文件夹访问权限")

        # 3. 固定添加"打开文件夹+"到最后一位
        self.ziyan_name_combo.addItem("打开文件夹+")

        # 4. 恢复之前选中的有效版本（跳过"打开文件夹+"）
        if saved_version:
            valid_index = self.ziyan_name_combo.findText(saved_version)
            if valid_index >= 0:
                self.ziyan_name_combo.setCurrentIndex(valid_index)
            else:
                # 保存的版本已被删除，默认选中第0项（若有有效文件）
                if self.ziyan_name_combo.count() > 1:
                    self.ziyan_name_combo.setCurrentIndex(0)
        else:
            # 无保存版本，默认选中第0项（若有有效文件）
            if self.ziyan_name_combo.count() > 1:
                self.ziyan_name_combo.setCurrentIndex(0)

    def start_ziyan_attack(self):
        if hasattr(self, 'ziyan_window'):
            self.ziyan_window.close()
            self.ziyan_window.deleteLater()
        mode_mapping = {
            "混合模式": "mixed",
            "全随机模式": "random",
            "洪水模式": "flood",
            "慢连接模式": "slowloris",
            "异步模式": "async"
        }
        current_english_mode = mode_mapping.get(self.ziyan_mode_combo.currentText(),
                                                self.ziyan_mode_combo.currentText())

        connection_mode_mapping = {
            "自动": "auto",
            "普通模式": "normal",
            "长连接模式": "long"
        }
        current_english_connection_mode = connection_mode_mapping.get(self.ziyan_connection_mode.currentText(),
                                                                      self.ziyan_connection_mode.currentText())

        config_data = {
            "kami": kami_config.get_kami(),
            "target": self.ziyan_target_url.text(),
            "mode": current_english_mode,
            "workers": self.ziyan_task_count.text(),
            "duration": self.ziyan_time.text(),
            "console": self.ziyan_console_mode.isChecked(),
            "no_local_proxy": not self.ziyan_local_proxy.isChecked(),
            "no_proxy": not self.ziyan_enable_proxy.isChecked(),
            "cloud_proxy": self.ziyan_cloud_proxy.isChecked(),
            "auto_workers": self.ziyan_auto_workers.isChecked(),
            "connection_mode": current_english_connection_mode,
            "local_proxy": "./配置文件_系统配置/proxy.txt",
        }

        if self.ziyan_all_time.isChecked():
            config_data['duration'] = "0"

        exe_name = self.ziyan_name_combo.currentText()

        # 构建exe路径
        try:
            from main import ROOT_DIR
            exe_path = f"gui/Go/{exe_name}"
        except ImportError:
            # 如果无法导入全局路径，则使用相对路径作为后备
            exe_path = f"gui/Go/{exe_name}"

        # 创建并显示新窗口（改为无父窗口的独立窗口）
        self.ziyan_window = ZiyanWindow(config=config_data, exe_name=exe_path, parent=self)
        self.ziyan_window.show()

    def createHelpTab(self):
        help = QWidget()
        help_layout = QVBoxLayout()

        # 创建可选中文本的QTextEdit控件
        help_text = QTextEdit()
        help_text.setFixedHeight(650)
        help_text.setReadOnly(True)  # 设置为只读
        help_text.setPlainText("\n".join([
            "功能说明：",
            "1.目标URL：填写你要测试的网站，如 https://example.com，协议需要填写完整（必须带 http:// 或 https://），支持HTTP/HTTPS/WebSocket协议，建议直接复制浏览器网址栏目标URL。",
            "2.压测模式：混合模式（推荐）：多种模式混合进行，自动检测网站连通性，动态切换模式；HTTP洪水模式：只进行洪水模式，达到快速消耗服务器CPU、内存等资源的效果；全随机模式：随机时长切换模式；慢连接模式：建立连接后缓慢发送请求，逐步消耗目标网站最大连接数。",
            "3.并发数：同时请求的数量，通过协程方式提升本地并发能力。16h16g配置建议区间20000-80000，网络上传速率50M以上可压制大部分网站服务器。",
            "4.持续时间：压力测试运行时间，单位秒。",
            "5.无限时间：勾选后运行时长为无限时间，不停止；不勾选则运行时长为持续时间的填写值",
            "6.版本：选择 ziyan_v版本号.exe ，如果提示版本过时可以在启动后控制台的提示消息中获取新版下载地址，或在说明-贡献中官网链接下载，获得新版程序后点击下拉框打开文件夹导入程序。不要改变程序名字，否则可能影响程序启动。",
            "7.控制台模式：启动程序后显示控制台，在控制台中可以看到实时状态和提示消息，建议勾选。",
            "8.启用代理服务：使用代理，不勾选则不使用代理，直接走本机ip，建议勾选。",
            "9.启用本地代理ip：使用本地代理ip文件，可以在代理ip分页中填写代理ip，无需启动代理ip测试，本程序运行前会自动进行ip可用性检测。",
            "10.官方云端代理ip：作者提供的高质量云端匿名代理ip，大幅提升压测效果。",
            "11.低伤害模式：根据核心数分配安全并发数。",
            "12.连接模式：不同于压测模式，对每一次压测请求方式进行模式选择，默认自动模式（推荐），长短连接混合进行；普通模式为只进行短连接模式，不进行长连接；长连接模式：只进行长连接。",
            "13.进程守护：监测模块运行状态。",
            "",
            "本工具的上限取决于你的网络带宽上传速率的上限，上传速率1Gbps以上可击垮大部分服务器。",
            "",
            f"当前版本: {config_value.current_version}"
        ]))

        # 设置文本交互标志，允许鼠标和键盘选择
        help_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse |
            Qt.TextSelectableByKeyboard
        )

        # 隐藏边框和背景
        help_text.setFrameShape(QFrame.NoFrame)  # 无边框
        help_text.setStyleSheet("background: transparent;")  # 透明背景

        # 设置自动换行
        help_text.setWordWrapMode(QTextOption.WordWrap)

        # 添加到布局
        help_layout.addWidget(help_text)
        help_layout.addStretch()
        help.setLayout(help_layout)
        self.tab_widget.addTab(help, "压力模块说明")

    def on_start_btn_action(self):
        # 切换状态标志
        self.ziyan_is_started = not self.ziyan_is_started

        if self.ziyan_is_started:  # 现在是启动状态
            # 更新按钮为停止状态
            self.ziyan_start_button.setText("停止")
            self.ziyan_start_button.setIcon(QIcon("gui/img/tingzhi.png"))
        else:  # 现在是停止状态
            # 恢复按钮为启动状态
            self.ziyan_start_button.setText("启动")
            self.ziyan_start_button.setIcon(QIcon("gui/img/qidong.png"))

        self.ziyan_start_button.setStyleSheet("""
            QPushButton {
                font-size: 25px;
            }
        """)
        self.ziyan_start_button.updateGeometry()