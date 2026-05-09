"""
版本迁移工具 - ikun联盟数据备份
用于在不同目录之间复制配置文件和数据，实现版本迁移
"""
import os
import shutil
from pathlib import Path
from datetime import datetime
from loguru import logger


class VersionMigration:
    """版本迁移管理类"""

    # 需要备份的文件夹列表
    BACKUP_FOLDERS = [
        "配置文件_实拍图配置",
        "配置文件_工具配置表",
        "配置文件_系统配置",
        "配置文件_成本",
        "配置文件_结算导出",
        "配置文件_财务汇总",
        "浏览器文件"
    ]

    def __init__(self, path_1: str = "", path_2: str = "", custom_backup_path: str = ""):
        """
        初始化版本迁移工具

        :param path_1: 源数据目录（包含上述文件夹的目录）
        :param path_2: 目标迁移目录（将备份文件复制到此目录）
        :param custom_backup_path: 自定义备份路径，默认为桌面
        """
        self.path_1 = path_1  # 源目录
        self.path_2 = path_2  # 目标迁移目录
        self.db_closed = False  # 数据库关闭状态标记

        # 桌面备份目录名称
        self.backup_folder_name = "ikun联盟数据备份"

        # 如果指定了自定义备份路径，使用自定义路径；否则使用桌面路径
        if custom_backup_path:
            self.backup_path = custom_backup_path
        else:
            self.backup_path = self._get_desktop_backup_path()

    def _get_desktop_backup_path(self) -> str:
        """获取桌面备份目录的绝对路径"""
        home = os.path.expanduser("~")
        desktop = os.path.join(home, "Desktop" if os.name == "nt" else "桌面")
        return os.path.join(desktop, self.backup_folder_name)

    def _close_database(self):
        """关闭数据库连接，确保数据库文件完整"""
        try:
            from config.common_config import global_db_close
            global_db_close()
            self.db_closed = True
            logger.info("✅ 数据库已安全关闭，可以操作数据库文件")
            return True
        except Exception as e:
            logger.error(f"❌ 关闭数据库失败: {e}")
            return False

    def _reconnect_database(self):
        """重新连接数据库"""
        try:
            # 重新初始化数据库连接（通过重新导入触发）
            import importlib
            from config import common_config
            importlib.reload(common_config)

            logger.info("✅ 数据库已重新连接")
            self.db_closed = False
            return True
        except Exception as e:
            logger.error(f"❌ 重新连接数据库失败: {e}")
            return False

    def _create_backup_dir(self) -> bool:
        """创建桌面备份目录"""
        try:
            if not os.path.exists(self.backup_path):
                os.makedirs(self.backup_path)
                logger.info(f"✅ 创建备份目录: {self.backup_path}")
            return True
        except Exception as e:
            logger.error(f"❌ 创建备份目录失败: {e}")
            return False

    def backup_to_desktop(self, progress_callback=None) -> dict:
        """
        功能1: 将指定文件夹从path_1复制到桌面备份目录

        操作流程：
        1. 关闭数据库（合并WAL缓存）
        2. 复制文件夹
        3. 重新连接数据库

        :param progress_callback: 进度回调函数，参数为 (current, total, message)
        :return: 操作结果字典
        """
        result = {
            "success": False,
            "message": "",
            "backup_path": self.backup_path,
            "copied_folders": [],
            "failed_folders": []
        }

        if not self.path_1:
            result["message"] = "❌ path_1未设置，请先设置源目录路径"
            return result

        if not os.path.exists(self.path_1):
            result["message"] = f"❌ 源目录不存在: {self.path_1}"
            return result

        # 步骤1：关闭数据库
        logger.info("=" * 60)
        logger.info("🔒 步骤1: 关闭数据库，准备备份...")
        logger.info("=" * 60)
        if not self._close_database():
            logger.warning("⚠️ 数据库关闭失败，继续备份操作（可能导致数据不完整）")
        else:
            # 等待文件系统刷新
            import time
            time.sleep(0.5)

        # 创建备份目录
        if not self._create_backup_dir():
            result["message"] = "❌ 创建备份目录失败"
            # 尝试重新连接数据库
            self._reconnect_database()
            return result

        # 清空备份目录（可选，根据需求决定是否保留历史）
        self._clear_backup_dir()

        # 步骤2：复制各个文件夹
        logger.info("=" * 60)
        logger.info("📦 步骤2: 开始复制文件夹...")
        logger.info("=" * 60)
        copied_count = 0
        total_folders = len(self.BACKUP_FOLDERS)
        
        for idx, folder in enumerate(self.BACKUP_FOLDERS, 1):
            # 更新进度
            if progress_callback:
                progress_callback(idx, total_folders, f"正在复制: {folder}")
            
            source_path = os.path.join(self.path_1, folder)
            target_path = os.path.join(self.backup_path, folder)

            if not os.path.exists(source_path):
                logger.warning(f"⚠️ 文件夹不存在，跳过: {folder}")
                result["failed_folders"].append(folder)
                continue

            try:
                # 使用带进度的复制方法
                self._copy_folder_with_progress(source_path, target_path, folder, progress_callback)
                result["copied_folders"].append(folder)
                copied_count += 1
                logger.info(f"✅ 复制成功: {folder}")
            except Exception as e:
                logger.error(f"❌ 复制失败 {folder}: {e}")
                result["failed_folders"].append(folder)

        result["success"] = copied_count > 0
        result["message"] = f"✅ 备份完成: 成功{copied_count}个, 失败{len(result['failed_folders'])}个"

        # 步骤3：重新连接数据库
        logger.info("=" * 60)
        logger.info("🔄 步骤3: 重新连接数据库...")
        logger.info("=" * 60)
        if not self._reconnect_database():
            logger.warning("⚠️ 数据库重连失败，请重启程序确保数据一致性")

        logger.info(f"📋 备份操作完成: {result['message']}")
        return result

    def _copy_folder_with_progress(self, source_path, target_path, folder_name, progress_callback=None):
        """
        复制文件夹并显示进度
        
        :param source_path: 源路径
        :param target_path: 目标路径
        :param folder_name: 文件夹名称
        :param progress_callback: 进度回调函数
        """
        import threading
        import time
        
        # 如果是浏览器文件，需要特殊处理进度显示
        is_browser_folder = "浏览器" in folder_name or "browser" in folder_name.lower()
        
        if is_browser_folder:
            # 浏览器文件使用模拟进度显示
            self._copy_browser_folder_with_simulated_progress(source_path, target_path, folder_name, progress_callback)
        else:
            # 普通文件夹直接复制
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            shutil.copytree(source_path, target_path)
            
            # 模拟进度更新
            if progress_callback:
                progress_callback(1, 1, f"✅ 复制成功: {folder_name}")
    
    def _copy_browser_folder_with_simulated_progress(self, source_path, target_path, folder_name, progress_callback=None):
        """
        复制浏览器文件夹并显示模拟进度（不影响性能）
        
        :param source_path: 源路径
        :param target_path: 目标路径
        :param folder_name: 文件夹名称
        :param progress_callback: 进度回调函数
        """
        import threading
        import time
        import random
        
        # 删除目标文件夹
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        
        # 估算文件数量（用于模拟进度）
        estimated_items = 0
        for root, dirs, files in os.walk(source_path):
            estimated_items += len(files) + len(dirs)
        
        # 如果文件数量很少，直接复制
        if estimated_items < 50:
            shutil.copytree(source_path, target_path)
            if progress_callback:
                progress_callback(100, 100, f"✅ 浏览器文件复制完成: {estimated_items} 项")
            return
        
        # 使用后台线程进行实际复制
        copy_complete = threading.Event()
        copy_success = [True]
        copy_error = [None]
        
        def actual_copy():
            try:
                shutil.copytree(source_path, target_path)
            except Exception as e:
                copy_success[0] = False
                copy_error[0] = e
            finally:
                copy_complete.set()
        
        # 启动后台复制线程
        copy_thread = threading.Thread(target=actual_copy)
        copy_thread.daemon = True
        copy_thread.start()
        
        # 模拟进度显示（不影响实际复制速度）
        simulated_progress = 0
        last_update = time.time()
        
        while not copy_complete.is_set():
            current_time = time.time()
            
            # 每0.1秒更新一次进度
            if current_time - last_update >= 0.1:
                # 模拟进度增长，使用随机增量让进度看起来自然
                increment = random.randint(1, 5)
                simulated_progress = min(simulated_progress + increment, 95)  # 最多到95%，等待实际完成
                
                if progress_callback:
                    progress_callback(simulated_progress, 100, f"🌐 正在复制浏览器文件... {simulated_progress}%")
                
                last_update = current_time
            
            # 短暂休眠，避免CPU占用过高
            time.sleep(0.05)
        
        # 等待复制线程完成
        copy_thread.join(timeout=1)
        
        # 检查复制结果
        if not copy_success[0]:
            raise copy_error[0] if copy_error[0] else Exception("浏览器文件复制失败")
        
        # 显示完成进度
        if progress_callback:
            progress_callback(100, 100, f"✅ 浏览器文件复制完成: {estimated_items} 项")

    def _clear_backup_dir(self):
        """清空备份目录"""
        try:
            if os.path.exists(self.backup_path):
                for item in os.listdir(self.backup_path):
                    item_path = os.path.join(self.backup_path, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                logger.info("🧹 清空备份目录完成")
        except Exception as e:
            logger.error(f"❌ 清空备份目录失败: {e}")

    def migrate_to_path2(self, progress_callback=None) -> dict:
        """
        功能2: 将桌面备份目录的内容复制到path_2

        操作流程：
        1. 关闭数据库（防止数据库文件被占用）
        2. 检查并删除目标目录中需要迁移的文件夹（防止冲突）
        3. 复制备份内容到目标目录
        4. 重新连接数据库

        :param progress_callback: 进度回调函数，参数为 (current, total, message)
        :return: 操作结果字典
        """
        result = {
            "success": False,
            "message": "",
            "source_path": self.backup_path,
            "target_path": self.path_2,
            "copied_folders": [],
            "failed_folders": [],
            "deleted_folders": []
        }

        if not self.path_2:
            result["message"] = "❌ path_2未设置，请先设置目标迁移目录路径"
            return result

        if not os.path.exists(self.backup_path):
            result["message"] = f"❌ 备份目录不存在: {self.backup_path}，请先执行backup_to_desktop()"
            return result

        # 步骤1：关闭数据库（必须关闭才能覆盖数据库文件）
        logger.info("=" * 60)
        logger.info("🔒 步骤1: 关闭数据库，准备迁移...")
        logger.info("=" * 60)
        if not self._close_database():
            logger.warning("⚠️ 数据库关闭失败，继续迁移操作（可能导致迁移失败）")
        else:
            # 等待文件系统刷新
            import time
            time.sleep(0.5)

        # 创建目标目录
        try:
            if not os.path.exists(self.path_2):
                os.makedirs(self.path_2)
                logger.info(f"✅ 创建目标目录: {self.path_2}")
        except Exception as e:
            result["message"] = f"❌ 创建目标目录失败: {e}"
            # 尝试重新连接数据库
            self._reconnect_database()
            return result

        # 步骤2：检查并删除目标目录中需要迁移的文件夹（防止冲突）
        logger.info("=" * 60)
        logger.info("🧹 步骤2: 检查并删除目标目录中的同名文件夹...")
        logger.info("=" * 60)
        deleted_count = 0
        try:
            # 遍历备份目录中的所有项目
            for item in os.listdir(self.backup_path):
                target_item = os.path.join(self.path_2, item)

                # 如果目标目录中存在同名文件夹或文件，先删除
                if os.path.exists(target_item):
                    try:
                        if os.path.isdir(target_item):
                            logger.info(f"🗑️ 删除目标目录中的文件夹: {item}")
                            shutil.rmtree(target_item)
                        else:
                            logger.info(f"🗑️ 删除目标目录中的文件: {item}")
                            os.remove(target_item)
                        result["deleted_folders"].append(item)
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"❌ 删除失败 {item}: {e}")
                        result["failed_folders"].append(f"删除失败-{item}")

            if deleted_count > 0:
                logger.info(f"✅ 已删除 {deleted_count} 个冲突项，防止迁移冲突")
            else:
                logger.info("✅ 目标目录中没有冲突项，可以正常迁移")

        except Exception as e:
            logger.error(f"❌ 删除目标目录冲突项失败: {e}")
            # 继续尝试迁移，不中断流程

        # 步骤3：复制备份目录内容到目标目录
        logger.info("=" * 60)
        logger.info("📦 步骤3: 开始迁移文件夹...")
        logger.info("=" * 60)
        copied_count = 0
        try:
            backup_items = os.listdir(self.backup_path)
            total_items = len(backup_items)
            
            for idx, item in enumerate(backup_items, 1):
                # 更新进度
                if progress_callback:
                    progress_callback(idx, total_items, f"正在迁移: {item}")
                
                source_item = os.path.join(self.backup_path, item)
                target_item = os.path.join(self.path_2, item)

                try:
                    if os.path.isdir(source_item):
                        # 再次检查并删除目标文件夹（防止并发冲突）
                        if os.path.exists(target_item):
                            shutil.rmtree(target_item)
                        # 使用带进度的复制方法
                        self._copy_folder_with_progress(source_item, target_item, item, progress_callback)
                    else:
                        # 再次检查并删除目标文件（防止并发冲突）
                        if os.path.exists(target_item):
                            os.remove(target_item)
                        shutil.copy2(source_item, target_item)

                    result["copied_folders"].append(item)
                    copied_count += 1
                    logger.info(f"✅ 迁移成功: {item}")
                except Exception as e:
                    logger.error(f"❌ 迁移失败 {item}: {e}")
                    result["failed_folders"].append(item)

            result["success"] = copied_count > 0
            result["message"] = f"✅ 迁移完成: 成功{copied_count}个, 失败{len(result['failed_folders'])}个"
            if deleted_count > 0:
                result["message"] += f" (已删除{deleted_count}个冲突项)"

        except Exception as e:
            result["message"] = f"❌ 迁移过程出错: {e}"
            logger.error(f"❌ 迁移过程出错: {e}")

        # 步骤4：重新连接数据库
        logger.info("=" * 60)
        logger.info("🔄 步骤4: 重新连接数据库...")
        logger.info("=" * 60)
        if not self._reconnect_database():
            logger.warning("⚠️ 数据库重连失败，请重启程序确保数据一致性")

        logger.info(f"📋 迁移操作完成: {result['message']}")
        return result

    def set_path_1(self, path: str):
        """设置源目录路径"""
        self.path_1 = path
        logger.info(f"📂 设置源目录: {path}")

    def set_path_2(self, path: str):
        """设置目标迁移目录路径"""
        self.path_2 = path
        logger.info(f"📂 设置目标目录: {path}")

    def get_backup_info(self) -> dict:
        """获取备份目录信息"""
        info = {
            "backup_path": self.backup_path,
            "backup_exists": os.path.exists(self.backup_path),
            "path_1": self.path_1,
            "path_1_exists": os.path.exists(self.path_1) if self.path_1 else False,
            "path_2": self.path_2,
            "path_2_exists": os.path.exists(self.path_2) if self.path_2 else False,
            "backup_folders": []
        }

        if info["backup_exists"]:
            try:
                info["backup_folders"] = os.listdir(self.backup_path)
            except Exception as e:
                logger.error(f"❌ 获取备份信息失败: {e}")

        return info


# ===== 简化版函数接口 =====

def backup_folders_to_desktop(path_1: str) -> dict:
    """
    简化版函数: 备份指定目录到桌面

    :param path_1: 源数据目录（包含上述文件夹的目录）
    :return: 操作结果字典
    """
    migrator = VersionMigration(path_1=path_1)
    return migrator.backup_to_desktop()


def migrate_to_target(path_2: str) -> dict:
    """
    简化版函数: 从桌面迁移到目标目录

    :param path_2: 目标迁移目录
    :return: 操作结果字典
    """
    migrator = VersionMigration(path_2=path_2)
    return migrator.migrate_to_path2()


# ===== 完整流程函数 =====

def full_migration_process(path_1: str, path_2: str) -> dict:
    """
    完整迁移流程: 从path_1备份到桌面，再从桌面迁移到path_2

    :param path_1: 源数据目录
    :param path_2: 目标迁移目录
    :return: 操作结果字典
    """
    migrator = VersionMigration(path_1=path_1, path_2=path_2)

    # 第一步: 备份到桌面
    logger.info("=" * 50)
    logger.info("📋 开始执行第一步: 备份到桌面")
    logger.info("=" * 50)
    result1 = migrator.backup_to_desktop()

    if not result1["success"]:
        return {
            "success": False,
            "message": f"备份失败: {result1['message']}",
            "step1": result1,
            "step2": None
        }

    # 第二步: 迁移到目标目录
    logger.info("=" * 50)
    logger.info("📋 开始执行第二步: 迁移到目标目录")
    logger.info("=" * 50)
    result2 = migrator.migrate_to_path2()

    return {
        "success": result2["success"],
        "message": f"完整迁移流程结束: {result2['message']}",
        "step1": result1,
        "step2": result2
    }


if __name__ == "__main__":
    # 测试代码
    # ===== 示例1: 设置固定路径 =====
    path_1 = r"D:\ikun联盟"  # 源目录路径，如: "d:/PythonProject/ikun_temu_system"
    path_2 = r"D:\ikun联盟-新"  # 目标迁移目录路径，如: "d:/new_version"

    # ===== 示例2: 使用简化版函数 =====
    # result = backup_folders_to_desktop(path_1)
    # print(result)

    # ===== 示例3: 完整迁移流程 =====
    result = full_migration_process(path_1, path_2)
    print(result)

    # ===== 示例4: 使用类实例进行分步操作 =====
    # migrator = VersionMigration(path_1=path_1, path_2=path_2)
    # info = migrator.get_backup_info()
    # print(info)

    # result1 = migrator.backup_to_desktop()
    # print("第一步结果:", result1)

    # result2 = migrator.migrate_to_path2()
    # print("第二步结果:", result2)

    logger.info("📋 版本迁移工具已就绪")
    logger.info(f"📂 待备份文件夹: {', '.join(VersionMigration.BACKUP_FOLDERS)}")