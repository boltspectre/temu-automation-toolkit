import json
import os
from pathlib import Path  # 新增：导入Path

import PIL
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError  # 新增：导入UnidentifiedImageError

# 1. 调高解压缩炸弹限制阈值
PIL.Image.MAX_IMAGE_PIXELS = 1000_000_000  # 设为3亿像素，高于当前图片的1.99亿


# ========================
# 全局工具函数（移出嵌套，确保能调用）
# ========================

def get_real_pic_config_dir():
    """获取实拍图配置目录的绝对路径，解决相对路径问题"""
    # 获取当前脚本所在目录（lite_modules）
    current_dir = Path(os.path.abspath(__file__)).parent
    # 向上两级到项目根目录（根据你的实际结构调整，确保能找到「配置文件_实拍图配置」）
    root_dir = current_dir.parent
    real_pic_dir = root_dir / "配置文件_实拍图配置"
    real_pic_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    return str(real_pic_dir)


def validate_and_fix_image(file_path):
    """
    验证图片有效性，若格式不兼容则自动转换为JPG
    :param file_path: 图片路径
    :return: 修复后的图片路径（或None）
    """
    # 1. 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误：图片文件不存在 → {file_path}")
        return None

    # 2. 检查文件是否为空
    if os.path.getsize(file_path) == 0:
        print(f"错误：图片文件为空 → {file_path}")
        return None

    # 3. 尝试打开图片并修复格式
    try:
        # 先尝试直接打开验证完整性
        with Image.open(file_path) as img:
            img.verify()

        # 转换为RGB模式（去除透明通道，避免PIL识别错误）
        img = Image.open(file_path).convert("RGB")
        # 若原文件不是JPG，自动转换并保存
        fixed_path = file_path
        if not file_path.lower().endswith(('.jpg', '.jpeg')):
            fixed_path = os.path.splitext(file_path)[0] + ".jpg"
            img.save(fixed_path, "JPEG", quality=95)
            print(f"提示：图片格式转换为JPG → {fixed_path}")
        return fixed_path

    except UnidentifiedImageError:
        print(f"错误：无法识别的图片格式 → {file_path} | 文件大小: {os.path.getsize(file_path) if os.path.exists(file_path) else '文件不存在'} bytes")
        return None
    except Exception as e:
        print(f"错误：图片验证失败 → {file_path} | 原因：{str(e)} | 异常类型: {type(e).__name__}")
        return None


def create_shop_folder(shop_name):
    ps_folder = os.path.join(os.getcwd(), "PS后")
    shop_folder = os.path.join(ps_folder, f"PS后_{shop_name}")
    os.makedirs(shop_folder, exist_ok=True)
    return shop_folder


def find_matching_image(label_name):
    """修改：使用绝对路径查找图片"""
    folder_path = get_real_pic_config_dir()  # 替换为绝对路径
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"标签图片文件夹不存在: {folder_path}")

    all_files = os.listdir(folder_path)
    target_prefix = label_name.lower()
    
    # 定义图片扩展名
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

    # 步骤1：优先匹配「文件名（去后缀）以label_name开头」的文件（仅限图片文件）
    for file in all_files:
        file_ext = os.path.splitext(file)[1].lower()
        # 只处理图片文件
        if file_ext not in image_extensions:
            continue
            
        file_name_without_ext = os.path.splitext(file)[0]
        if file_name_without_ext.lower().startswith(target_prefix):
            return os.path.join(folder_path, file)

    # 步骤2：兜底匹配「文件名（去后缀）包含label_name」的文件（仅限图片文件）
    for file in all_files:
        file_ext = os.path.splitext(file)[1].lower()
        # 只处理图片文件
        if file_ext not in image_extensions:
            continue
            
        file_name_without_ext = os.path.splitext(file)[0]
        if target_prefix in file_name_without_ext.lower():
            return os.path.join(folder_path, file)

    raise FileNotFoundError(
        f"未找到文件名（去后缀）以 '{label_name}' 开头/包含 '{label_name}' 的图片文件\n"
        f"文件夹内文件：{all_files}"
    )


# ========================
# 主逻辑
# ========================

def change_upload_pic_main(LABEL_NAME, PRODUCT_ID, PRODUCT_SKC_ID, json_data=None):
    try:
        if not json_data:
            # 修改：使用绝对路径加载配置文件
            config_path = os.path.join(get_real_pic_config_dir(), "sku.json")
            with open(config_path, "r", encoding="utf-8") as json_file:
                sku_data = json.load(json_file)
                MOCK_SKU_DATA = sku_data
        else:
            MOCK_SKU_DATA = json_data

        # 构建SKU映射
        skus_by_name = {}
        for sku_data in MOCK_SKU_DATA["skus"]:
            desc = next((d for d in MOCK_SKU_DATA["skuDescList"] if d["id"] == sku_data["descId"]), None)
            if not desc:
                continue

            # 同时存储原始名称和大小写不敏感的映射
            sku_name = sku_data["name"]
            skus_by_name[sku_name] = type('Sku', (), {
                'positionX': int(sku_data["positionX"]),  # 强制转整数，避免字符串坐标
                'positionY': int(sku_data["positionY"]),
                'font_size': int(sku_data["font_size"]),
                'oumentRepList': desc["oumentRepList"],
                'makerRepList': desc["makerRepList"],
            })()
            # 添加大小写不敏感的映射（如果原始名称是大写，也添加小写映射）
            if sku_name.isupper():
                skus_by_name[sku_name.lower()] = skus_by_name[sku_name]
            elif sku_name.islower():
                skus_by_name[sku_name.upper()] = skus_by_name[sku_name]

        # 检查SKU是否存在（支持大小写不敏感查找）
        selected_sku = skus_by_name.get(LABEL_NAME)
        if not selected_sku:
            # 尝试大小写转换后再次查找
            selected_sku = skus_by_name.get(LABEL_NAME.upper())
            if not selected_sku:
                selected_sku = skus_by_name.get(LABEL_NAME.lower())
            
            if not selected_sku:
                # 获取所有可用的SKU名称（去重）
                available_skus = list(set([k for k in skus_by_name.keys() if k == k.upper() or k == k.lower()]))
                error_msg = f"错误：未找到 SKU 名称为 '{LABEL_NAME}' 的配置 | 当前店铺缩写/LABEL_NAME: {LABEL_NAME} | 可用的SKU名称: {available_skus}"
                return False, error_msg

        # 2. 创建输出文件夹
        shop_folder = create_shop_folder(LABEL_NAME)
        output_path = os.path.join(shop_folder, f"{PRODUCT_ID}.png")

        # 3. 找到底图（使用绝对路径）
        base_image_path = find_matching_image(LABEL_NAME)
        # print(f"找到匹配图片：{base_image_path}")

        # 4. 验证并修复图片（核心修复）
        fixed_image_path = validate_and_fix_image(base_image_path)
        if not fixed_image_path:
            return False, f"图片验证失败 → {base_image_path} | 当前传入的店铺缩写/LABEL_NAME: {LABEL_NAME} | PRODUCT_ID: {PRODUCT_ID} | PRODUCT_SKC_ID: {PRODUCT_SKC_ID} 请检查sku.json配置是否存在或格式是否正确"

        # 5. 安全打开图片（替换原直接打开逻辑）
        image = Image.open(fixed_image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        # 6. 绘制文字
        position = (selected_sku.positionX, selected_sku.positionY)
        font_size = selected_sku.font_size

        # 尝试加载微软雅黑粗体，失败则用默认字体
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", font_size)
        except IOError:
            font = ImageFont.load_default()
            print("警告：无法加载微软雅黑字体，使用默认字体")

        draw.text(position, str(PRODUCT_SKC_ID), fill="black", font=font)

        # 7. 保存图片
        image.save(output_path, format="PNG")
        # print(f"✅ 标签图已生成并保存至: {output_path}")
        return True, output_path

    except Exception as e:
        error_msg = f"处理失败：{str(e)}"
        print(error_msg)
        return False, error_msg
