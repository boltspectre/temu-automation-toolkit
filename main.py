import asyncio
import sys
import traceback
from datetime import datetime, timedelta
import urllib3
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication
from loguru import logger
from qasync import QEventLoop
from config.common_config import config_manager, encryptor, global_db_close
from config.py_config import config_value, generate_version_number
from config.update_config import software_update_config
from config.permission_manager import permission_manager
from gui.LoginPage import LoginWindow
from gui.MainApp import MainStartApp
from lite_modules.del_img import delete_old_pictures
from lite_modules.print_logo import print_art_logo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== 全局异常处理函数 ==========
def handle_global_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理：记录到error.log后关闭数据库"""
    # 记录完整异常堆栈到error.log
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    error_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"\n{'='*60}\n[{error_time}] 全局异常:\n{error_msg}\n{'='*60}\n"

    # 写入error/error.log
    try:
        import os
        error_dir = "error"
        if not os.path.exists(error_dir):
            os.makedirs(error_dir)
        error_log_path = os.path.join(error_dir, "error.log")
        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"写入error.log失败: {e}")

    # 同时使用loguru记录
    logger.error(f"全局异常捕获: {exc_value}")
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).error("详细堆栈信息")

    # 执行数据库关闭
    try:
        global_db_close()
        logger.info("异常退出前数据库已安全关闭")
    except Exception as e:
        logger.error(f"数据库关闭失败: {e}")

# 设置全局异常捕获
sys.excepthook = handle_global_exception

# ========== 封装业务函数，避免顶层执行 ==========
def clean_images():
    TARGET_FOLDER = r"PS后"
    cutoff_datetime = datetime.now() - timedelta(hours=0.01)
    delete_old_pictures(TARGET_FOLDER, cutoff_datetime)

# ========== 核心：所有业务逻辑、QApplication初始化 移到main函数并放入__main__ ==========
def main(package_mode, login, code_project_mode_debug, project_debug, any_kami_login=0):
    software_update_config()
    print_art_logo()

    # 创建error文件夹
    import os
    error_dir = "error"
    if not os.path.exists(error_dir):
        os.makedirs(error_dir)
        logger.info(f"✅ 创建error文件夹: {error_dir}")

    # 打包模式判断
    if package_mode:
        login = 1
        project_debug = 0
        any_kami_login = 0
    
    # 任意卡密模式下，自动启用登录模式（但会绕过云端验证）
    if any_kami_login:
        login = 1

    # 只在非登录模式下保存权限（开发模式）
    if not login and not any_kami_login:
        code_project_mode_encrypt = encryptor.encrypt({"code_project_mode": str(code_project_mode_debug)})
        permission_manager.save_permissions(code_project_mode_debug)
    
    # 根据权限初始化数据库（仅在非登录模式下）
    permissions = code_project_mode_debug if (not login and not any_kami_login) else []
    
    if not login and not any_kami_login:
        # logger.info(f"当前权限: {permissions}")
        
        # 统一初始化所有数据库
        try:
            from config.common_config import initialize_all_databases
            success = initialize_all_databases(permissions)
            
            if success:
                logger.info("✅ 所有数据库初始化完成")
            else:
                logger.warning("⚠️ 部分数据库初始化失败")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
    elif any_kami_login:
        logger.info(f"任意卡密登录模式：权限为 {code_project_mode_debug}，数据库将在登录后初始化")
    else:
        logger.info("登录模式：数据库将在登录成功后初始化")
    
    # 启动日志清理执行器
    try:
        from utils.log_cleaner import start_log_cleaner_executor
        start_log_cleaner_executor()
    except Exception as e:
        logger.error(f"日志清理执行器启动失败: {e}")
    
    # 定时任务执行器将在服务器启动时启动，不在这里直接启动
    
    # 保存执行器引用，用于退出时清理
    log_cleaner_executor = None
    try:
        from utils.log_cleaner import get_log_cleaner_executor
        log_cleaner_executor = get_log_cleaner_executor()
    except Exception as e:
        logger.warning(f"获取执行器引用失败: {e}")

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    logger.remove()  # 移除默认的handler

    font = QFont("Microsoft YaHei", 12)
    app.setFont(font)

    # 启动事件循环
    with loop:
        if any_kami_login == 1:
            # 任意卡密登录模式（优先判断，绕过云端验证）
            try:
                logger.info(f"🔓 任意卡密登录模式已启用，权限: {code_project_mode_debug}")
                login_window = LoginWindow(any_kami_mode=True, code_project_mode_debug=code_project_mode_debug)
                login_window.show()
                clean_images()
            except Exception as e:
                error_msg = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                error_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_entry = f"\n{'='*60}\n[{error_time}] 任意卡密登录异常:\n{error_msg}\n{'='*60}\n"
                try:
                    import os
                    error_dir = "error"
                    if not os.path.exists(error_dir):
                        os.makedirs(error_dir)
                    error_log_path = os.path.join(error_dir, "error.log")
                    with open(error_log_path, "a", encoding="utf-8") as f:
                        f.write(log_entry)
                except Exception as e:
                    print(f"写入error.log失败: {e}")

                logger.error(e)
                logger.error("任意卡密登录失败")
                logger.opt(exception=True).error("详细堆栈信息")

                try:
                    global_db_close()
                    logger.info("异常退出前数据库已安全关闭")
                except Exception as db_e:
                    logger.error(f"数据库关闭失败: {db_e}")

                sys.exit(1)
        elif login == 1:
            # 正常登录启动（需要云端验证）
            try:
                login_window = LoginWindow()
                login_window.show()
                clean_images()
            except Exception as e:
                # 记录完整异常到error.log
                error_msg = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                error_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_entry = f"\n{'='*60}\n[{error_time}] 登录异常:\n{error_msg}\n{'='*60}\n"
                try:
                    import os
                    error_dir = "error"
                    if not os.path.exists(error_dir):
                        os.makedirs(error_dir)
                    error_log_path = os.path.join(error_dir, "error.log")
                    with open(error_log_path, "a", encoding="utf-8") as f:
                        f.write(log_entry)
                except Exception as e:
                    print(f"写入error.log失败: {e}")

                logger.error(e)
                logger.error("登录失败")
                logger.opt(exception=True).error("详细堆栈信息")

                # 执行全局数据库关闭
                try:
                    global_db_close()
                    logger.info("异常退出前数据库已安全关闭")
                except Exception as db_e:
                    logger.error(f"数据库关闭失败: {db_e}")

                sys.exit(1)
        else:
            # 直接启动主窗口
            window = MainStartApp(project_debug, code_project_mode_debug)
            window.show()
            clean_images()

        # 运行事件循环
        exit_code = loop.run_forever()
        
        # 退出前清理后台执行器
        logger.info("开始清理后台执行器...")
        
        try:
            if log_cleaner_executor is not None:
                from utils.log_cleaner import stop_log_cleaner_executor
                stop_log_cleaner_executor()
                logger.info("日志清理执行器已停止")
        except Exception as e:
            logger.error(f"停止日志清理执行器失败: {e}")
        
        # 停止定时任务执行器
        try:
            from utils.scheduled_task_executor import stop_scheduled_task_executor
            stop_scheduled_task_executor()
            logger.info("定时任务执行器已停止")
        except Exception as e:
            logger.error(f"停止定时任务执行器失败: {e}")
        
        # 关闭数据库
        try:
            global_db_close()
            logger.info("数据库已安全关闭")
        except Exception as e:
            logger.error(f"数据库关闭失败: {e}")
        
        logger.info(f"程序退出，退出代码: {exit_code}")
        sys.exit(exit_code if exit_code is not None else 0)

# ========== 入口保护：确保所有代码仅在主进程执行，且QApplication最先初始化 ==========
if __name__ == "__main__":

    # 是否开启打包模式 （打包环境下会自动 开启登录模式、关闭权限调试模式）需要配置 config_value.server_api_domain 并部署卡密管理系统，如果你没有部署卡密管理系统可以直接使用免密模式打包
    package_mode = 0

    # 非打包环境下 是否开启任意卡密登录模式（输入任意字符都可登录，权限由 code_project_mode_debug 决定）
    any_kami_login = 1

    # 非打包环境下 是否开启登录
    login = 0

    # 非打包环境下 是否开启权限调试模式
    project_debug = 0

    # 非打包环境下 自定义权限 "temu", "caiwu", "spider"

    # code_project_mode_debug = ["spider"]
    # code_project_mode_debug = ["temu", "caiwu"]
    code_project_mode_debug = ["temu", "caiwu", "spider"]
    # code_project_mode_debug = ["caiwu"]
    # code_project_mode_debug = ["temu"]

    if package_mode and config_value.current_version != generate_version_number():
        for i in range(5):
            logger.error("版本号不一致，生产环境打包请修改版本号")

        logger.warning(f"当前版本：{config_value.current_version} 请在点击current_version跳转并修改为：{generate_version_number()}")

    main(package_mode, login, code_project_mode_debug, project_debug, any_kami_login)