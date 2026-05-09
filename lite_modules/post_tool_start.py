import asyncio
import sys

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication
from qasync import QEventLoop

from gui.RequestsTool import RequestsTool

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 设置异步事件循环
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = RequestsTool()
    window.show()

    font = QFont("Microsoft YaHei", 12)
    app.setFont(font)

    with loop:
        sys.exit(loop.run_forever())