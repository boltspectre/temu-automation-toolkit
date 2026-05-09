from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel


class LockTool:
    def __init__(self, parent_widget, target_tab_index=None):
        self.parent = parent_widget
        self.target_tab_index = target_tab_index  # 要锁定的选项卡索引

        # 创建锁定覆盖层
        self.lock_overlay = QWidget(parent_widget)
        self.lock_overlay.setGeometry(parent_widget.rect())
        self.lock_overlay.setStyleSheet("background-color: rgba(28, 58, 128, 80);")
        self.lock_overlay.hide()

        # 锁定提示
        lock_label = QLabel("界面已锁定", self.lock_overlay)
        lock_label.setAlignment(Qt.AlignCenter)
        lock_label.setStyleSheet("""
            color: white; 
            font-size: 24px;
            background: transparent;
        """)
        lock_label.setGeometry(self.lock_overlay.rect())

    def set_locked(self, locked):
        """设置锁定状态，只对目标选项卡生效"""
        if self.target_tab_index is not None:
            current_tab = self.parent.tab_widget.currentIndex()
            if current_tab != self.target_tab_index:
                return  # 不是目标选项卡，不执行锁定

        if locked:
            print("Locking overlay...")
            self.lock_overlay.show()
            self.lock_overlay.raise_()
            # 只禁用目标选项卡中的控件
            target_tab = self.parent.tab_widget.widget(self.target_tab_index)
            for child in target_tab.findChildren(QWidget):
                if not isinstance(child, QLabel):
                    child.setEnabled(False)
        else:
            self.lock_overlay.hide()
            # 只启用目标选项卡中的控件
            target_tab = self.parent.tab_widget.widget(self.target_tab_index)
            for child in target_tab.findChildren(QWidget):
                child.setEnabled(True)

    def resize_event(self, event):
        """处理窗口大小变化"""
        self.lock_overlay.setGeometry(self.parent.rect())