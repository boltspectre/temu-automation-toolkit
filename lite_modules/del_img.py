import os
from datetime import datetime, timedelta
from typing import List, Set

from loguru import logger

from lite_modules.print_logo import print_art_logo


def get_all_img_paths_advanced(
        base_dir: str = "fixed_upload_img",
        img_extensions: Set[str] = None,
        recursive: bool = True  # 是否递归读取子文件夹
) -> List[str]:
    """
    进阶版：读取图片路径（支持递归、自定义后缀、去重）
    :param base_dir: 目标文件夹
    :param img_extensions: 自定义图片后缀集合（None则用默认）
    :param recursive: 是否递归读取子文件夹
    :return: 去重后的图片绝对路径列表
    """
    # 默认图片后缀（覆盖主流格式）
    DEFAULT_IMG_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg', '.ico'}
    img_exts = img_extensions if img_extensions else DEFAULT_IMG_EXT

    img_paths = set()  # 用集合去重
    if not os.path.exists(base_dir):
        logger.warning(f"⚠️ 固定上传文件夹不存在：{base_dir}")
        return []

    # 遍历文件夹（递归/非递归）
    for root, dirs, files in os.walk(base_dir):
        for filename in files:
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext in img_exts:
                abs_path = os.path.abspath(os.path.join(root, filename))
                img_paths.add(abs_path)

        # 如果不递归，只处理一级文件夹后退出
        if not recursive:
            break

    # 转为列表并排序
    sorted_paths = sorted(list(img_paths))
    # print(f"✅ 共找到 {len(sorted_paths)} 张图片（去重后）")
    return sorted_paths

# # 示例1：仅读取png/jpg，不递归
# img_paths_1 = get_all_img_paths_advanced(
#     img_extensions={'.png', '.jpg'},
#     recursive=False
# )
# print("仅PNG/JPG（非递归）：", img_paths_1)
#
# # 示例2：递归读取所有图片格式
# img_paths_2 = get_all_img_paths_advanced(recursive=True)
# print("所有图片（递归）：", img_paths_2)




def delete_old_pictures(folder_path, cutoff_datetime=None, log: bool = False):
    """
    删除指定文件夹（含所有子文件夹）中修改时间早于指定时间的图片文件
    :param folder_path: 目标文件夹路径（绝对/相对路径）
    :param cutoff_datetime: 截止时间（datetime对象），为None时默认当前时间-1小时
    :return: dict - 包含删除成功/失败的文件信息
    """
    # 定义需要过滤的图片后缀（已添加jpg和png）
    PICTURE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif')

    # 处理默认时间：当前时间减1小时
    if cutoff_datetime is None:
        cutoff_datetime = datetime.now() - timedelta(hours=1)

    # 转换截止时间为时间戳（用于和文件修改时间对比）
    cutoff_timestamp = cutoff_datetime.timestamp()
    cutoff_time_str = cutoff_datetime.strftime("%Y-%m-%d %H:%M:%S")
    if log:
        logger.info(f"🗑️ 清理规则：删除修改时间早于 {cutoff_time_str} 的图片文件")

    # 初始化返回结果
    result = {
        "deleted": [],  # 成功删除的文件
        "failed": [],  # 删除失败的文件（权限/文件不存在等）
        "skipped": []  # 跳过的文件（非图片/时间符合要求）
    }

    # 检查文件夹是否存在
    if not os.path.exists(folder_path):
        if log:
            logger.error(f"❌ 文件夹不存在：{folder_path}")
        return result

    # 记录总文件数和图片文件数
    total_files = 0
    picture_files = 0

    # 递归遍历文件夹中的所有文件（包含子文件夹）
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            total_files += 1
            file_path = os.path.join(root, filename)

            # 转换为小写判断后缀
            file_lower = filename.lower()

            # 检查是否为图片文件
            is_picture = False
            for suffix in PICTURE_SUFFIXES:
                if file_lower.endswith(suffix):
                    is_picture = True
                    picture_files += 1
                    break

            if not is_picture:
                result["skipped"].append(f"{file_path} - 非图片文件，跳过")
                continue

            try:
                # 获取文件的修改时间戳
                file_mtime = os.path.getmtime(file_path)
                # 转换为可读时间
                file_mtime_str = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d %H:%M:%S")

                # 判断是否早于截止时间
                if file_mtime < cutoff_timestamp:
                    # 删除文件
                    os.remove(file_path)
                    result["deleted"].append(f"{file_path} - 修改时间：{file_mtime_str}，已删除")
                else:
                    result["skipped"].append(f"{file_path} - 修改时间：{file_mtime_str}，晚于截止时间，跳过")

            except PermissionError:
                result["failed"].append(f"{file_path} - 权限不足，无法删除")
                print(f"❌ 权限不足：{file_path}")
            except FileNotFoundError:
                result["failed"].append(f"{file_path} - 文件已不存在")
                print(f"❌ 文件不存在：{file_path}")
            except Exception as e:
                result["failed"].append(f"{file_path} - 删除失败：{str(e)}")
                print(f"❌ 删除失败：{file_path} - {str(e)}")

    return result


# nuitka ^
# --standalone ^
# --output-dir=dist ^
# --output-filename=IKUN图片清理大师.exe ^
# --remove-output ^
# --show-scons ^
# --windows-icon-from-ico=favicon.ico ^
# --include-data-files=favicon.ico=favicon.ico ^
# --nofollow-import-to=pytest ^
# --nofollow-import-to=unittest ^
# --nofollow-import-to=setuptools ^
# --nofollow-import-to=pip ^
# --nofollow-import-to=tkinter ^
# --nofollow-import-to=distutils ^
# --nofollow-import-to=pydoc ^
# --nofollow-import-to=doctest ^
# del_img.py

# ====== 改进的使用示例 ======
if __name__ == "__main__":
    # 1. 配置参数
    # TARGET_FOLDER = r"D:\PythonProject\ikun_temu_system/PS后/"
    cutoff_datetime = datetime.now() - timedelta(hours=1)
    TARGET_FOLDER_list = []

    print("======== 欢迎使用【IKUN图片清理大师】========")
    print_art_logo()

    print("========================================")
    while True:
        print("🐔 开始清理配置文件夹下的所有图片，该操作会自动遍历文件夹下的所有子文件夹")

        try:
            with open("del_img_confi1g.txt", "r", encoding="utf-8") as f:
                path_list = f.read().split("\n")
        except FileNotFoundError:
            print("配置文件不存在，请创建del_img_config.txt文件，并填写待处理的文件夹路径，每行一个")
            input("创建后请按回车键继续...")

        print("待处理文件夹：")
        for TARGET_FOLDER in path_list:
            print(f"🐔 {TARGET_FOLDER}")
            TARGET_FOLDER_list.append(TARGET_FOLDER)

        choice = input("是否处理？(y/n)：").strip().lower()
        for TARGET_FOLDER in TARGET_FOLDER_list:
            print(f"开始处理文件夹：{TARGET_FOLDER}")
            delete_result = delete_old_pictures(TARGET_FOLDER, log=True)