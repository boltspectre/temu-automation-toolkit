"""
窗口尺寸适配工具
提供统一的窗口尺寸自适应功能
"""
from PyQt5.QtWidgets import QApplication
from loguru import logger


def adapt_window_size(window, base_width, base_height, base_screen_width=2560):
    """
    动态适配窗口尺寸：以2560分辨率为基准，等比例适配当前分辨率
    支持2560/1920/3840（4K）等所有桌面分辨率
    
    参数:
        window: QWidget/QMainWindow 窗口对象
        base_width: int 基准窗口宽度（在2560分辨率下的宽度）
        base_height: int 基准窗口高度（在2560分辨率下的高度）
        base_screen_width: int 基准屏幕宽度，默认2560
    """
    # 获取当前桌面主屏幕分辨率
    screen = QApplication.primaryScreen()
    current_w = screen.size().width()  # 当前屏幕宽度
    
    # 计算缩放比例（按宽度等比例）
    scale_ratio = current_w / base_screen_width
    
    # 计算当前分辨率的窗口尺寸（取整，保证像素为整数）
    target_win_w = int(base_width * scale_ratio)
    target_win_h = int(base_height * scale_ratio)
    
    # 动态设置窗口尺寸
    window.resize(target_win_w, target_win_h)
    
    # 打印日志，便于调试
    logger.info(f"当前屏幕分辨率：{current_w}×{screen.size().height()}，适配窗口尺寸：{target_win_w}×{target_win_h}")
