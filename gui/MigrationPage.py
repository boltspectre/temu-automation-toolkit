"""
版本迁移页面 - 单独窗口
用于数据备份和迁移
使用 data.json 存储配置，避免占用数据库连接
"""
import json
import os
import sys
import subprocess
import time
import requests
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QMessageBox, QTextEdit,
    QScrollArea, QFrame, QFileDialog, QApplication, QDialog,
    QProgressBar
)
from loguru import logger

# 导入 FlowLayout 和窗口适配工具
from gui.HelpPage import FlowLayout
from gui.utils.window_adapter import adapt_window_size
from gui.utils.encryptData import CryptoUtils
from config.py_config import config_value
from modules.machine_code import get_unique_machine_code


class ProgressDialog(QDialog):
    """进度条对话框"""
    
    def __init__(self, parent=None, title="正在处理"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(450, 120)
        
        layout = QVBoxLayout(self)
        
        # 标签
        self.label = QLabel("正在处理...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
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
        layout.addWidget(self.progress_bar)
    
    def update_progress(self, current, total, message):
        """更新进度"""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.label.setText(message)
            QApplication.processEvents()  # 强制刷新UI
    
    def update_sub_progress(self, sub_percent, sub_message):
        """更新子进度（用于大文件复制）"""
        # 只更新进度条和消息，不显示百分比数字
        self.progress_bar.setValue(sub_percent)
        self.label.setText(sub_message)
        QApplication.processEvents()  # 强制刷新UI
    
    def set_browser_mode(self):
        """设置为浏览器文件模式，显示特殊提示"""
        self.label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF6B35;")


class MigrationWindow(QMainWindow):
    """版本迁移窗口"""

    # 需要备份的文件夹列表
    DEFAULT_FOLDERS = [
        "配置文件_实拍图配置",
        "配置文件_工具配置表",
        "配置文件_系统配置",
        "配置文件_成本",
        "配置文件_结算导出",
        "配置文件_财务汇总",
        "浏览器文件"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("版本迁移工具")
        self.setWindowIcon(QIcon('gui/img/favicon.ico'))
        
        # 使用统一的窗口尺寸适配函数，基准尺寸：1200×900（2560分辨率下）
        adapt_window_size(self, 1200, 900)
        
        # 关闭数据库连接，避免迁移时冲突
        try:
            from config.common_config import global_db_close
            global_db_close()
            logger.info("✅ 版迁移窗口打开，数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库失败: {e}")
        
        self.initUI()

    def closeEvent(self, event):
        """窗口关闭事件"""
        event.accept()
        
        # 确保数据库连接已关闭
        try:
            from config.common_config import global_db_close
            global_db_close()
            logger.info("✅ 版迁移窗口关闭，数据库连接已确保关闭")
        except Exception as e:
            logger.error(f"关闭数据库失败: {e}")

    def initUI(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = QLabel("版本迁移工具 - 用于数据备份和迁移")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 路径设置区域
        path_group = QGroupBox("路径设置")
        path_layout = QVBoxLayout()

        # 旧版程序地址
        old_path_layout = QHBoxLayout()
        old_path_label = QLabel("旧版程序地址：")
        old_path_label.setFixedWidth(120)
        self.old_path_edit = QLineEdit()
        self.old_path_edit.setPlaceholderText("自动获取程序根目录")
        old_path_layout.addWidget(old_path_label)
        old_path_layout.addWidget(self.old_path_edit)

        default_old_btn = QPushButton("默认")
        default_old_btn.setIcon(QIcon("gui/img/tijiao.png"))
        default_old_btn.clicked.connect(self.set_default_old_path)
        old_path_layout.addWidget(default_old_btn)

        old_path_btn = QPushButton("...")
        old_path_btn.clicked.connect(self.select_old_path)
        old_path_layout.addWidget(old_path_btn)
        path_layout.addLayout(old_path_layout)

        # 新版程序地址
        new_path_layout = QHBoxLayout()
        new_path_label = QLabel("新版程序地址：")
        new_path_label.setFixedWidth(120)
        self.new_path_edit = QLineEdit()
        self.new_path_edit.setPlaceholderText("默认与旧版程序地址相同")
        new_path_layout.addWidget(new_path_label)
        new_path_layout.addWidget(self.new_path_edit)

        default_new_btn = QPushButton("默认")
        default_new_btn.setIcon(QIcon("gui/img/tijiao.png"))
        default_new_btn.clicked.connect(self.set_default_new_path)
        new_path_layout.addWidget(default_new_btn)

        new_path_btn = QPushButton("...")
        new_path_btn.clicked.connect(self.select_new_path)
        new_path_layout.addWidget(new_path_btn)
        path_layout.addLayout(new_path_layout)

        # 备份保存地址
        backup_path_layout = QHBoxLayout()
        backup_path_label = QLabel("备份保存地址：")
        backup_path_label.setFixedWidth(120)
        self.backup_path_edit = QLineEdit()
        backup_path_layout.addWidget(backup_path_label)
        backup_path_layout.addWidget(self.backup_path_edit)

        open_folder_btn = QPushButton("打开")
        open_folder_btn.setIcon(QIcon("gui/img/zuidahua.png"))
        open_folder_btn.clicked.connect(self.open_backup_folder)
        backup_path_layout.addWidget(open_folder_btn)

        desktop_btn = QPushButton("桌面")
        desktop_btn.setIcon(QIcon("gui/img/tijiao.png"))
        desktop_btn.clicked.connect(self.set_desktop_backup_path)
        backup_path_layout.addWidget(desktop_btn)

        backup_path_btn = QPushButton("...")
        backup_path_btn.clicked.connect(self.select_backup_path)
        backup_path_layout.addWidget(backup_path_btn)
        path_layout.addLayout(backup_path_layout)

        # 保存配置按钮
        save_btn_layout = QHBoxLayout()
        save_btn_layout.addStretch()
        save_btn = QPushButton("保存配置")
        save_btn.setIcon(QIcon("gui/img/baochun.png"))
        save_btn.clicked.connect(self.save_migration_config)
        save_btn_layout.addWidget(save_btn)
        save_btn_layout.addStretch()
        path_layout.addLayout(save_btn_layout)

        path_group.setLayout(path_layout)
        main_layout.addWidget(path_group)

        # 文件夹列表区域
        folders_group = QGroupBox("需要迁移的文件夹")
        folders_layout = QVBoxLayout()

        # 流式布局容器
        self.flow_container = QWidget()
        self.flow_layout = FlowLayout(self.flow_container)
        self.flow_layout.setSpacing(15)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.flow_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)
        scroll_area.setMaximumHeight(300)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: #f9f9f9;
            }
        """)
        folders_layout.addWidget(scroll_area)

        # 按钮区域
        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("重置")
        reset_btn.setIcon(QIcon("gui/img/shuaxin.png"))
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #F59E0B;
                color: white;
                font-size: 16px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #D97706;
            }
            QPushButton:pressed {
                background-color: #B45309;
            }
        """)
        reset_btn.clicked.connect(self.reset_migration_folders)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()

        add_folder_btn = QPushButton("添加文件夹")
        add_folder_btn.setIcon(QIcon("gui/img/fuzhi.png"))
        add_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366F1;
                color: white;
                font-size: 16px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #4338CA;
            }
        """)
        add_folder_btn.clicked.connect(self.add_migration_folder)
        btn_layout.addWidget(add_folder_btn)
        folders_layout.addLayout(btn_layout)

        folders_group.setLayout(folders_layout)
        main_layout.addWidget(folders_group)

        # 说明文字
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMinimumHeight(200)
        info_text.setPlainText("\n".join([
            "使用说明：",
            "1. 备份数据：将旧版程序地址下配置文件、浏览器文件等文件夹备份到备份保存地址",
            "2. 版本迁移：将备份保存地址的数据迁移到新版程序地址",
            "3. 文件地址：选择文件夹的所在目录，例如程序根目录：D:\\ikun联盟，配置文件目录：D:\\ikun联盟\\配置文件_系统配置",
            "旧版和新版程序地址一样是正常的",
            "",
            "注意事项：",
            "- 卸载旧版前请先执行'数据备份'",
            "- 安装新版后执行'版本迁移'恢复数据",
            "- 版本迁移时会自动删除目标目录中同名的文件夹，防止冲突",
            "- 默认备份位置：桌面/ikun联盟数据备份 文件夹",
            "- 配置自动保存到备份文件夹的 data.json 文件中",
            "",
            "文件夹说明：",
            "- 配置文件_实拍图配置：存放实拍图相关配置",
            "- 配置文件_工具配置表：存放核价相关配置",
            "- 配置文件_系统配置：存放系统相关配置和数据库",
            "- 配置文件_成本：存放成本表格和成本完善表",
            "- 配置文件_结算导出：存放导出的财务数据",
            "- 配置文件_财务汇总：存放财务汇总报表",
            "- 浏览器文件：存放浏览器用户数据",
            "",
            "版本更新教程：",
            "第一步：旧版程序备份",
            "  - 确保旧版程序正常运行，能够正常访问所有功能",
            "  - 打开登录页的版本迁移工具窗口",
            "  - 确认'旧版程序地址'、'备份保存地址'设置正确",
            "  - 确认'需要迁移的文件夹'列表包含所有中文文件夹",
            "  - 点击'数据备份'按钮，等待备份完成",
            "  - 备份完成后，建议检查备份文件夹确认文件已成功复制",
            "",
            "第二步：卸载旧版程序并安装新版程序",
            "  - 关闭旧版程序所有窗口，确保程序完全退出",
            "  - 卸载旧版程序（通过控制面板或直接删除安装目录）",
            "  - 下载最新版程序安装包",
            "  - 运行安装程序，按照提示完成安装",
            "  - 安装完成后，不要立即运行程序，继续下一步",
            "",
            "第三步：执行版本迁移恢复数据",
            "  - 启动新版程序，打开登录页",
            "  - 点击登录页的'版本迁移'按钮打开迁移工具",
            "  - 确认'新版程序地址'指向新安装的版本目录",
            "  - 确认'备份保存地址'指向第一步备份的文件夹",
            "  - 确认'需要迁移的文件夹'列表正确",
            "  - 点击'版本迁移'按钮，等待迁移完成",
            "  - 迁移完成后，建议检查新版程序目录确认数据已恢复",
            "",
            "重要提示：",
            "- 备份和迁移过程中会自动关闭数据库连接，请不要强制关闭程序",
            "- 如果备份数据量较大，可能需要较长时间，请耐心等待",
            "- 建议在迁移前对整个程序目录做一次完整备份（可使用压缩软件打包）",
            "- 如果迁移失败，可以手动将备份的文件复制到新版目录"
        ]))
        info_text.setFrameShape(QFrame.NoFrame)
        info_text.setStyleSheet("background: #f5f5f5; border-radius: 5px;")
        main_layout.addWidget(info_text)

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        # 清理进程按钮
        clean_btn = QPushButton("清理ikun进程")
        clean_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: white;
                font-size: 20px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 15px 30px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
            QPushButton:pressed {
                background-color: #991B1B;
            }
        """)
        clean_btn.clicked.connect(self.clean_python_processes)
        btn_layout.addWidget(clean_btn)

        btn_layout.addSpacing(50)

        # 解绑卡密按钮
        unbind_btn = QPushButton("解绑卡密")
        unbind_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 20px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 15px 30px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #495057;
            }
        """)
        unbind_btn.clicked.connect(self.unbind_card)
        btn_layout.addWidget(unbind_btn)

        btn_layout.addSpacing(50)

        # 数据备份按钮
        backup_btn = QPushButton("数据备份")
        backup_btn.setStyleSheet("""
            QPushButton {
                background-color: #0B78F4;
                color: white;
                font-size: 20px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 15px 30px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #0966D4;
            }
            QPushButton:pressed {
                background-color: #0858BC;
            }
        """)
        backup_btn.clicked.connect(self.backup_data)
        btn_layout.addWidget(backup_btn)

        btn_layout.addSpacing(50)

        # 版本迁移按钮
        migrate_btn = QPushButton("版本迁移")
        migrate_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 20px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 15px 30px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        migrate_btn.clicked.connect(self.migrate_data)
        btn_layout.addWidget(migrate_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # 初始化数据
        self.init_migration_paths()
        self.init_migration_folders()

    def get_program_root(self):
        """获取程序根目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        program_root = os.path.dirname(current_dir)
        return program_root.replace('/', '\\')

    def get_data_json_path(self):
        """获取 data.json 文件路径"""
        backup_path = self.backup_path_edit.text().strip()
        if not backup_path:
            # 默认使用桌面备份路径
            home = os.path.expanduser("~")
            desktop = os.path.join(home, "Desktop" if os.name == "nt" else "桌面")
            backup_path = os.path.join(desktop, "ikun联盟数据备份")
        return os.path.join(backup_path, "data.json")

    def load_from_data_json(self):
        """从 data.json 加载配置"""
        try:
            data_json_path = self.get_data_json_path()
            if os.path.exists(data_json_path):
                with open(data_json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"从 data.json 加载配置失败: {e}")
        return None

    def save_to_data_json(self, data):
        """保存配置到 data.json"""
        try:
            data_json_path = self.get_data_json_path()
            # 确保备份目录存在
            backup_path = os.path.dirname(data_json_path)
            os.makedirs(backup_path, exist_ok=True)

            with open(data_json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存配置到 data.json 失败: {e}")
            return False

    def init_migration_paths(self):
        """初始化迁移路径 - 从 data.json 读取"""
        program_root = self.get_program_root()

        # 默认值
        old_path = program_root
        new_path = program_root
        home = os.path.expanduser("~")
        desktop = os.path.join(home, "Desktop" if os.name == "nt" else "桌面")
        backup_path = os.path.join(desktop, "ikun联盟数据备份")

        # 先尝试从 data.json 读取
        data = self.load_from_data_json()
        if data:
            old_path = data.get("old_path", old_path)
            new_path = data.get("new_path", new_path)
            backup_path = data.get("backup_path", backup_path)

        self.old_path_edit.setText(old_path.replace('/', '\\'))
        self.new_path_edit.setText(new_path.replace('/', '\\'))
        self.backup_path_edit.setText(backup_path.replace('/', '\\'))

    def init_migration_folders(self):
        """初始化迁移文件夹列表 - 从 data.json 读取"""
        folders = self.DEFAULT_FOLDERS.copy()

        # 尝试从 data.json 读取
        data = self.load_from_data_json()
        if data and "folders" in data:
            folders = data["folders"]

        self.clear_folder_cards()
        for folder in folders:
            self.create_folder_card(folder)

    def clear_folder_cards(self):
        """清空文件夹卡片"""
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def create_folder_card(self, folder_name):
        """创建文件夹卡片"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 5px;
            }
            QFrame:hover {
                background-color: #f0f9ff;
                border-color: #0B78F4;
            }
        """)
        card.setFixedSize(240, 60)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 文件夹图标
        folder_icon = QLabel("📁")
        folder_icon.setStyleSheet("font-size: 20px;")
        layout.addWidget(folder_icon)

        # 文件夹名称
        label = QLabel(folder_name)
        label.setStyleSheet("""
            font-size: 12px;
            color: #333;
            font-weight: 500;
        """)
        label.setWordWrap(True)
        label.setMaximumWidth(150)
        layout.addWidget(label, stretch=1)

        # 删除按钮（X）
        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #999;
                font-size: 20px;
                border: none;
                border-radius: 12px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #fee2e2;
                color: #ef4444;
            }
            QPushButton:pressed {
                background-color: #fecaca;
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_folder_card(card, folder_name))
        layout.addWidget(delete_btn)

        self.flow_layout.addWidget(card)

    def delete_folder_card(self, card, folder_name):
        """删除文件夹卡片"""
        self.flow_layout.removeWidget(card)
        card.deleteLater()
        self.save_folders_to_config()

    def get_current_folders(self):
        """获取当前文件夹列表"""
        folders = []
        for i in range(self.flow_layout.count()):
            widget = self.flow_layout.itemAt(i).widget()
            if widget:
                label = widget.findChild(QLabel)
                if label and label.text() != "📁":  # 排除图标标签
                    # 如果找到多个标签，取最后一个（文件夹名称）
                    pass
                # 重新查找所有标签
                labels = widget.findChildren(QLabel)
                for lbl in labels:
                    if lbl.text() != "📁" and lbl.text():  # 排除图标标签
                        folders.append(lbl.text())
                        break
        return folders

    def save_folders_to_config(self):
        """保存文件夹列表到 data.json"""
        folders = self.get_current_folders()
        data = self.load_from_data_json() or {}
        data["folders"] = folders
        self.save_to_data_json(data)

    def add_migration_folder(self):
        """添加迁移文件夹"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("选择要迁移的文件夹")
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)

        if dialog.exec_():
            selected_dir = dialog.selectedFiles()[0]
            folder_name = os.path.basename(selected_dir)

            existing_folders = self.get_current_folders()
            if folder_name in existing_folders:
                QMessageBox.warning(self, "重复添加", f"文件夹 '{folder_name}' 已存在！")
                return

            self.create_folder_card(folder_name)
            self.save_folders_to_config()

    def reset_migration_folders(self):
        """重置迁移文件夹"""
        reply = QMessageBox.question(
            self, '确认重置',
            f'确定要将文件夹列表重置为默认值吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.clear_folder_cards()
        for folder in self.DEFAULT_FOLDERS:
            self.create_folder_card(folder)
        self.save_folders_to_config()
        QMessageBox.information(self, "重置成功", "文件夹列表已重置为默认值！")

    def set_default_old_path(self):
        """设置旧版程序地址为默认"""
        reply = QMessageBox.question(
            self, '确认设置',
            '确定要将旧版程序地址设置为默认路径吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            program_root = self.get_program_root()
            self.old_path_edit.setText(program_root)
            self.save_migration_config()

    def set_default_new_path(self):
        """设置新版程序地址为默认"""
        reply = QMessageBox.question(
            self, '确认设置',
            '确定要将新版程序地址设置为默认路径吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            program_root = self.get_program_root()
            self.new_path_edit.setText(program_root)
            self.save_migration_config()

    def select_old_path(self):
        """选择旧版程序路径"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("选择旧版程序文件夹")
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec_():
            selected_dir = dialog.selectedFiles()[0].replace('/', '\\')
            self.old_path_edit.setText(selected_dir)
            self.save_migration_config()

    def select_new_path(self):
        """选择新版程序路径"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("选择新版程序文件夹")
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec_():
            selected_dir = dialog.selectedFiles()[0].replace('/', '\\')
            self.new_path_edit.setText(selected_dir)
            self.save_migration_config()

    def set_desktop_backup_path(self):
        """设置备份路径为桌面"""
        reply = QMessageBox.question(
            self, '确认设置',
            '确定要将备份路径设置为桌面吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            home = os.path.expanduser("~")
            desktop = os.path.join(home, "Desktop" if os.name == "nt" else "桌面")
            backup_dir = os.path.join(desktop, "ikun联盟数据备份").replace('/', '\\')
            self.backup_path_edit.setText(backup_dir)
            self.save_migration_config()

    def select_backup_path(self):
        """选择备份路径"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("选择备份保存文件夹")
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        if dialog.exec_():
            selected_dir = dialog.selectedFiles()[0].replace('/', '\\')
            self.backup_path_edit.setText(selected_dir)
            self.save_migration_config()

    def open_backup_folder(self):
        """打开备份文件夹"""
        backup_path = self.backup_path_edit.text().strip()
        if not backup_path:
            QMessageBox.warning(self, "路径为空", "备份路径为空！")
            return
        if not os.path.exists(backup_path):
            QMessageBox.warning(self, "路径不存在", f"备份文件夹不存在：\n{backup_path}")
            return
        try:
            if os.name == 'nt':
                os.startfile(backup_path)
            else:
                subprocess.call(['open', backup_path])
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开文件夹：{str(e)}")

    def save_migration_config(self):
        """保存版本迁移配置到 data.json"""
        old_path = self.old_path_edit.text().strip()
        new_path = self.new_path_edit.text().strip()
        backup_path = self.backup_path_edit.text().strip()
        folders = self.get_current_folders()

        data = {
            "old_path": old_path,
            "new_path": new_path,
            "backup_path": backup_path,
            "folders": folders if folders else self.DEFAULT_FOLDERS
        }

        if self.save_to_data_json(data):
            QMessageBox.information(self, "保存成功", "版本迁移配置已保存到 data.json！")
        else:
            QMessageBox.critical(self, "保存失败", "保存配置到 data.json 失败！")

    def backup_data(self):
        """执行数据备份"""

        from config.common_config import global_db_close
        global_db_close()

        old_path = self.old_path_edit.text().strip()
        backup_path = self.backup_path_edit.text().strip()

        if not old_path or not os.path.exists(old_path):
            QMessageBox.warning(self, "路径错误", "旧版程序地址不存在！")
            return

        folders = self.get_current_folders()
        if not folders:
            QMessageBox.warning(self, "文件夹列表为空", "请先添加需要迁移的文件夹！")
            return

        reply = QMessageBox.question(
            self, '确认备份',
            f'确定要备份数据到指定位置吗？\n\n源目录：{old_path}\n备份到：{backup_path}\n\n备份文件夹：{len(folders)}个',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # 创建进度条对话框
            progress_dialog = ProgressDialog(self, "正在备份数据...")
            progress_dialog.show()
            
            # 先关闭数据库
            from config.common_config import global_db_close
            global_db_close()

            from utils.version_migration import VersionMigration
            migrator = VersionMigration(path_1=old_path, custom_backup_path=backup_path)
            migrator.BACKUP_FOLDERS = folders
            
            # 使用进度回调
            result = migrator.backup_to_desktop(progress_callback=progress_dialog.update_progress)

            # 关闭进度条对话框
            progress_dialog.close()

            # 备份完成后保存配置到
            new_path = self.new_path_edit.text().strip()
            data = {
                "old_path": old_path,
                "new_path": new_path,
                "backup_path": backup_path,
                "folders": folders
            }
            if self.save_to_data_json(data):
                logger.info(f"✅ 配置已保存到 {self.get_data_json_path()}")

            # 重新连接数据库
            import importlib
            from config import common_config
            importlib.reload(common_config)
            logger.info("✅ 数据库已重新连接")

            if result["success"]:
                QMessageBox.information(self, "备份成功", result["message"])
            else:
                QMessageBox.warning(self, "备份失败", result["message"])
        except Exception as e:
            # 尝试重新连接数据库
            try:
                import importlib
                from config import common_config
                importlib.reload(common_config)
            except:
                pass
            QMessageBox.critical(self, "备份异常", f"备份过程出错：{str(e)}")

    def migrate_data(self):
        """执行版本迁移"""

        from config.common_config import global_db_close
        global_db_close()

        backup_path = self.backup_path_edit.text().strip()
        new_path = self.new_path_edit.text().strip()

        if not backup_path or not os.path.exists(backup_path):
            QMessageBox.warning(self, "路径错误", "备份目录不存在，请先执行数据备份！")
            return

        if not new_path:
            QMessageBox.warning(self, "路径错误", "新版程序地址不能为空！")
            return

        if not os.path.exists(new_path):
            QMessageBox.warning(self, "路径错误", "新版程序地址不存在！")
            return

        folders = self.get_current_folders()
        if not folders:
            QMessageBox.warning(self, "文件夹列表为空", "请先添加需要迁移的文件夹！")
            return

        reply = QMessageBox.question(
            self, '确认迁移',
            f'确定要将备份数据迁移到新版程序吗？\n\n备份来源：{backup_path}\n目标目录：{new_path}\n\n迁移文件夹：{len(folders)}个',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # 创建进度条对话框
            progress_dialog = ProgressDialog(self, "正在迁移数据...")
            progress_dialog.show()
            
            # 先关闭数据库
            from config.common_config import global_db_close
            global_db_close()

            from utils.version_migration import VersionMigration
            migrator = VersionMigration(path_1=backup_path, path_2=new_path, custom_backup_path=backup_path)
            migrator.BACKUP_FOLDERS = folders
            
            # 使用进度回调
            result = migrator.migrate_to_path2(progress_callback=progress_dialog.update_progress)
            
            # 关闭进度条对话框
            progress_dialog.close()

            # 重新连接数据库
            import importlib
            from config import common_config
            importlib.reload(common_config)
            logger.info("✅ 数据库已重新连接")

            if result["success"]:
                QMessageBox.information(self, "迁移成功", result["message"])
            else:
                QMessageBox.warning(self, "迁移失败", result["message"])
        except Exception as e:
            # 尝试重新连接数据库
            try:
                import importlib
                from config import common_config
                importlib.reload(common_config)
            except:
                pass
            QMessageBox.critical(self, "迁移异常", f"迁移过程出错：{str(e)}")

    def clean_python_processes(self):
        """清理所有名称包含ikun的应用程序"""
        reply = QMessageBox.question(
            self, '确认清理',
            '确定要关闭所有名称包含ikun的应用程序吗？\n\n这将关闭所有正在运行的ikun相关程序，包括当前程序。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            from modules.close_all import kill_ikun_processes_with_delay
            # 使用新的延迟清理函数，它会先显示弹窗，然后分步骤清理进程
            # 注意：这个函数会终止当前进程，所以后续代码可能不会执行
            kill_ikun_processes_with_delay()
            # 如果进程没有被终止，显示成功信息
            QMessageBox.information(self, "击落ikun", "ikun进程清理完成")
        except Exception as e:
            QMessageBox.critical(self, "清理失败", f"清理ikun进程时出错：{str(e)}")

    def unbind_card(self):
        """解绑卡密功能"""
        # 从配置文件_系统配置目录读取卡密
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "配置文件_系统配置", "config.txt")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                current_kami = config_data.get("kami", "")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取配置文件失败：{str(e)}")
            return
        
        if not current_kami:
            QMessageBox.warning(self, "错误", "配置文件中未找到卡密，无法执行解绑操作")
            return
            
        dialog = QDialog(self)
        reply = QMessageBox.question(
            dialog, '确认解绑',
            f'确定要解绑设备吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        timestamp = int(time.time())
        raw_machine_code = get_unique_machine_code()
        
        # 检查机器码是否为None，如果是则返回错误
        if not raw_machine_code:
            QMessageBox.warning(self, "错误", "无法获取机器码，请检查系统权限或重启软件")
            return
            
        machine_code = f"{config_value.prefix_token}-{raw_machine_code}"
        encrypted_machine_code = CryptoUtils.encrypt_data(machine_code)
        encrypted_kami = CryptoUtils.encrypt_data(current_kami)
        signature = CryptoUtils.generate_signature(current_kami, timestamp)
        payload = {
            'encrypted_kami': encrypted_kami,
            'timestamp': timestamp,
            'signature': signature,
            'encrypted_machine_code': encrypted_machine_code
        }
        api_url = f"{config_value.server_api_domain}/api/jiebang.php?static_token={config_value.static_token}"
        proxies = {"http": None, "https": None}
        try:
            response = requests.post(api_url, data=payload, proxies=proxies)
            resp_data = response.json()
            if resp_data.get('code') == 1:
                QMessageBox.information(self, '解绑成功', '解绑成功，程序将退出')
                # 清除配置文件中的卡密
                try:
                    config_data["kami"] = ""
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"清除配置文件卡密失败: {e}")
                # 退出程序（使用全局实例，与HelpPage保持一致）
                QApplication.instance().quit()
            else:
                error_msg = resp_data.get('msg', '解绑失败')
                QMessageBox.warning(self, '解绑失败', error_msg)
        except requests.exceptions.RequestException as e:
            QMessageBox.warning(self, '网络错误', f"解绑请求失败：{str(e)}")
            return
        except json.JSONDecodeError:
            QMessageBox.warning(self, '解析错误', '服务器返回数据格式异常，解绑失败')
            return


def show_migration_window(parent=None):
    """显示版本迁移窗口"""
    window = MigrationWindow(parent)
    window.show()
    return window


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MigrationWindow()
    window.show()
    sys.exit(app.exec_())