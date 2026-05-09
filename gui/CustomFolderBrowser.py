import os
import shutil
import subprocess
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QIcon, QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
                             QLabel, QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                             QMenu, QAction, QInputDialog)


class CustomFileManager(QWidget):
    file_changed_signal = pyqtSignal()

    def __init__(self, folder_path: Path, title: str = "文件管理器"):
        super().__init__()
        self.folder_path = folder_path
        self.copy_source = None  # 用于存储复制的源文件路径
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon("gui/img/favicon.ico"))  # 替换为你的图标路径
        self.resize(700, 500)
        self.init_ui()
        # 启用拖放功能
        self.setAcceptDrops(True)
        self.file_list.setAcceptDrops(True)

    def init_ui(self):
        # 顶部路径和操作按钮
        top_layout = QHBoxLayout()

        # 路径显示
        self.path_label = QLabel(f"当前路径: {self.folder_path}")
        top_layout.addWidget(self.path_label)
        top_layout.addStretch()  # 拉伸项，将按钮推到右侧

        # 上传按钮
        self.upload_btn = QPushButton("上传文件")
        self.upload_btn.clicked.connect(self.upload_files)
        top_layout.addWidget(self.upload_btn)

        # 返回上级按钮
        self.back_btn = QPushButton("返回上级")
        self.back_btn.clicked.connect(self.go_back)
        top_layout.addWidget(self.back_btn)

        # 文件夹内容列表
        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QListWidget.DragDrop)
        self.file_list.itemDoubleClicked.connect(self.on_item_double_click)
        self.load_folder_contents()

        # 状态提示
        self.status_label = QLabel("提示: 可双击打开文件/文件夹，或拖拽文件到窗口上传")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")

        # 初始化右键菜单
        self.init_context_menu()

        # 整体布局
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.file_list)
        main_layout.addWidget(self.status_label)
        self.setLayout(main_layout)

    def init_context_menu(self):
        """创建右键菜单及菜单项"""
        self.context_menu = QMenu(self)

        # 删除文件/文件夹
        self.delete_action = QAction("删除", self)
        self.delete_action.triggered.connect(self.on_delete)
        self.context_menu.addAction(self.delete_action)

        # 复制文件/文件夹
        self.copy_action = QAction("复制", self)
        self.copy_action.triggered.connect(self.on_copy)
        self.context_menu.addAction(self.copy_action)

        # 粘贴文件/文件夹
        self.paste_action = QAction("粘贴", self)
        self.paste_action.triggered.connect(self.on_paste)
        self.context_menu.addAction(self.paste_action)

        # 重命名文件/文件夹
        self.rename_action = QAction("重命名", self)
        self.rename_action.triggered.connect(self.on_rename)
        self.context_menu.addAction(self.rename_action)

        # 为文件列表绑定右键菜单
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_context_menu)

        # 记录当前选中的项目（用于后续操作）
        self.selected_item = None

    def show_context_menu(self, position: QPoint):
        """右键点击时显示菜单"""
        # 获取当前选中的项目
        self.selected_item = self.file_list.itemAt(position)
        if self.selected_item:
            # 禁用粘贴功能（仅在有复制源时启用）
            self.paste_action.setEnabled(self.copy_source is not None)
            # 显示菜单（位置为鼠标点击处）
            self.context_menu.exec_(self.file_list.mapToGlobal(position))

    def load_folder_contents(self):
        """加载文件夹内容并显示"""
        self.file_list.clear()
        if not self.folder_path.exists():
            self.file_list.addItem("文件夹不存在")
            return

        # 先添加上级目录（如果存在）
        if self.folder_path.parent != self.folder_path:  # 不是根目录
            parent_item = QListWidgetItem("📁 上级目录")
            parent_item.setData(Qt.UserRole, str(self.folder_path.parent))
            self.file_list.addItem(parent_item)

        # 遍历当前目录
        for item in self.folder_path.iterdir():
            list_item = QListWidgetItem()

            # 设置图标和显示文本
            if item.is_dir():
                list_item.setText(f"📁 {item.name}")
                list_item.setIcon(QIcon.fromTheme("folder", QIcon("icons/folder.png")))
            else:
                # 根据文件类型显示不同图标
                ext = item.suffix.lower()
                if ext in ['exe', 'bat']:
                    list_item.setText(f"🔧 {item.name}")
                elif ext in ['txt', 'md']:
                    list_item.setText(f"📄 {item.name}")
                elif ext in ['png', 'jpg', 'jpeg', 'gif']:
                    list_item.setText(f"🖼️ {item.name}")
                else:
                    list_item.setText(f"📎 {item.name}")
                list_item.setIcon(QIcon.fromTheme("file", QIcon("icons/file.png")))

            list_item.setData(Qt.UserRole, str(item))
            self.file_list.addItem(list_item)

    def on_item_double_click(self, item: QListWidgetItem):
        """双击打开文件或文件夹"""
        full_path = Path(item.data(Qt.UserRole))
        if full_path.is_dir():
            # 进入子文件夹
            self.folder_path = full_path
            self.path_label.setText(f"当前路径: {full_path}")
            self.load_folder_contents()
            self.file_changed_signal.emit()
        else:
            # 用系统默认程序打开文件
            try:
                if sys.platform.startswith('win32'):
                    os.startfile(full_path)
                elif sys.platform.startswith('darwin'):
                    subprocess.run(['open', str(full_path)], check=True)
                else:
                    subprocess.run(['xdg-open', str(full_path)], check=True)
            except Exception as e:
                QMessageBox.warning(self, "打开失败", f"无法打开文件: {str(e)}")

    def go_back(self):
        """返回上级目录"""
        if self.folder_path.parent != self.folder_path:  # 不是根目录
            self.folder_path = self.folder_path.parent
            self.path_label.setText(f"当前路径: {self.folder_path}")
            self.load_folder_contents()
            self.file_changed_signal.emit()
        else:
            QMessageBox.information(self, "提示", "已经是根目录")

    def upload_files(self):
        """通过文件选择对话框上传文件"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择要上传的文件")
        if files:
            self.copy_files_to_target(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """处理拖入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """处理放下事件（接收拖拽的文件）"""
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.copy_files_to_target(files)
            event.acceptProposedAction()

    def copy_files_to_target(self, files):
        """将文件复制到当前目录"""
        success_count = 0
        fail_count = 0

        for file_path in files:
            src = Path(file_path)
            if not src.exists():
                fail_count += 1
                continue

            dest = self.folder_path / src.name

            # 处理文件已存在的情况
            if dest.exists():
                reply = QMessageBox.question(
                    self, "文件已存在",
                    f"文件 {src.name} 已存在，是否覆盖？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    fail_count += 1
                    continue

            try:
                # 复制文件
                if src.is_file():
                    shutil.copy2(src, dest)  # 保留元数据的复制
                    success_count += 1
                else:
                    # 递归复制文件夹
                    shutil.copytree(src, dest, dirs_exist_ok=True)  # dirs_exist_ok=True 支持覆盖
                    success_count += 1
            except Exception as e:
                QMessageBox.warning(self, "复制失败", f"无法复制 {src.name}: {str(e)}")
                fail_count += 1

        # 显示上传结果
        self.status_label.setText(
            f"上传完成: 成功 {success_count} 个，失败 {fail_count} 个"
        )
        # 刷新文件列表

        self.load_folder_contents()
        self.file_changed_signal.emit()

    # 右键菜单功能实现
    def on_delete(self):
        """删除选中的文件/文件夹"""
        if not self.selected_item:
            return
        full_path = Path(self.selected_item.data(Qt.UserRole))
        if not full_path.exists():
            QMessageBox.warning(self, "错误", "文件/文件夹不存在")
            return

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {full_path.name} 吗？\n删除后无法恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if full_path.is_file():
                os.remove(full_path)  # 删除文件
            else:
                shutil.rmtree(full_path)  # 递归删除文件夹
            self.status_label.setText(f"已删除: {full_path.name}")
            self.load_folder_contents()  # 刷新列表
            self.file_changed_signal.emit()
        except Exception as e:
            QMessageBox.warning(self, "删除失败", f"无法删除 {full_path.name}: {str(e)}")

    def on_copy(self):
        """复制选中的文件/文件夹"""
        if not self.selected_item:
            return
        self.copy_source = Path(self.selected_item.data(Qt.UserRole))
        if not self.copy_source.exists():
            QMessageBox.warning(self, "错误", "复制源不存在")
            self.copy_source = None
            return
        self.status_label.setText(f"已复制: {self.copy_source.name}")

    def on_paste(self):
        """粘贴复制的文件/文件夹到当前目录"""
        if not self.copy_source or not self.copy_source.exists():
            QMessageBox.warning(self, "错误", "没有可粘贴的文件/文件夹")
            return

        dest = self.folder_path / self.copy_source.name

        # 处理文件已存在的情况
        if dest.exists():
            reply = QMessageBox.question(
                self, "文件已存在",
                f"文件 {self.copy_source.name} 已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        try:
            if self.copy_source.is_file():
                shutil.copy2(self.copy_source, dest)  # 复制文件
            else:
                shutil.copytree(self.copy_source, dest, dirs_exist_ok=True)  # 复制文件夹
            self.status_label.setText(f"已粘贴: {self.copy_source.name}")
            self.load_folder_contents()  # 刷新列表
            self.file_changed_signal.emit()
        except Exception as e:
            QMessageBox.warning(self, "粘贴失败", f"无法粘贴 {self.copy_source.name}: {str(e)}")

    def on_rename(self):
        """重命名选中的文件/文件夹"""
        if not self.selected_item:
            return
        full_path = Path(self.selected_item.data(Qt.UserRole))
        if not full_path.exists():
            QMessageBox.warning(self, "错误", "文件/文件夹不存在")
            return

        # 获取新名称
        new_name, ok = QInputDialog.getText(
            self, "重命名",
            f"请输入新名称（当前: {full_path.name}）:",
            text=full_path.name
        )
        if not ok or not new_name.strip():
            return  # 取消或空名称
        new_name = new_name.strip()

        # 构建新路径
        new_path = full_path.parent / new_name

        # 检查新名称是否已存在
        if new_path.exists():
            QMessageBox.warning(self, "错误", f"名称 {new_name} 已存在")
            return

        try:
            os.rename(full_path, new_path)  # 重命名
            self.status_label.setText(f"已重命名: {full_path.name} → {new_name}")
            self.load_folder_contents()  # 刷新列表
            self.file_changed_signal.emit()
        except Exception as e:
            QMessageBox.warning(self, "重命名失败", f"无法重命名: {str(e)}")


# 测试代码（可单独运行）
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # 测试路径：当前目录
    window = CustomFileManager(folder_path=Path("."), title="带右键菜单的文件管理器")
    window.show()
    sys.exit(app.exec_())
