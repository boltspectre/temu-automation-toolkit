import os
import re
import subprocess
import sys
import time
from typing import List, Dict, Set, Tuple
from typing import Optional

import pandas as pd
import psutil
from loguru import logger


def validate_and_merge_cost_table(
        factory_mapping_file: str,  # 厂家名称映射表文件路径（一列：厂家名称）
        cost_file: str,  # 待融合的成本表文件路径
        output_file: str,  # 融合后成本表的输出路径
        factory_col: str = "厂家名称",  # 成本表中厂家名称列名
        skc_col: str = "SKC货号",  # 成本表中SKC货号列名
        sku_col: str = "SKU属性",  # 成本表中SKU属性列名
        jit_cost_col: str = "jit成本",  # 成本表中jit成本列名
        vmi_cost_col: str = "vmi成本"  # 成本表中vmi成本列名
) -> dict:
    """
    1. 校验厂家名称映射表：无重复/包含关系，一行内的厂家用中英文逗号分割
    2. 根据映射表融合成本表：将同一组厂家的行合并为该组的【完整行名称】（如"鳕峰（新地址），鳕峰沥水垫"）
    """
    # ===================== 步骤1：读取并解析厂家名称映射表 =====================
    try:
        # 读取厂家映射表（仅一列）
        factory_df = pd.read_excel(factory_mapping_file, header=0)
        if factory_df.shape[1] != 1:
            raise ValueError(f"厂家名称映射表必须仅包含一列！当前列数：{factory_df.shape[1]}")

        factory_col_name = factory_df.columns[0]
        # 去重空值行
        factory_df = factory_df.dropna(subset=[factory_col_name]).reset_index(drop=True)
        if len(factory_df) == 0:
            raise ValueError("厂家名称映射表无有效数据！")

        # 核心修正：存储【完整行名称】+ 组内厂家列表
        factory_group_info: List[Dict] = []  # 存储每组信息 [{"full_name":完整行名, "factories":[厂家1,厂家2]}, ...]
        all_factory_set: Set[str] = set()  # 存储所有厂家，用于校验重复/包含

        for idx, row in factory_df.iterrows():
            full_factory_str = str(row[factory_col_name]).strip()
            if not full_factory_str:
                continue

            # 分割（中英文逗号）+ 去重 + 去空格
            factories = re.split(r'[,，]', full_factory_str)
            factories = [f.strip() for f in factories if f.strip()]

            if not factories:
                logger.warning(f"厂家映射表第{idx + 1}行无有效厂家名称，已跳过")
                continue

            # 校验当前组内厂家是否与已有厂家重复/包含
            conflict_flag = False
            for f in factories:
                # 检查是否重复
                if f in all_factory_set:
                    logger.error(f"❌ 厂家名称重复：'{f}' 同时出现在多行中！")
                    conflict_flag = True
                    break

                # 检查包含关系（如"鳕峰"包含于"鳕峰新地址"）
                for exist_f in all_factory_set:
                    if f in exist_f or exist_f in f:
                        logger.error(f"❌ 厂家名称包含冲突：'{f}' 与 '{exist_f}' 存在包含关系！")
                        conflict_flag = True
                        break
                if conflict_flag:
                    break

            if conflict_flag:
                return {
                    "code": -1,
                    "msg": f"厂家名称映射表第{idx + 1}行存在重复/包含冲突，终止操作",
                    "data": None
                }

            # 核心修正：存储完整行名称 + 组内厂家
            factory_group_info.append({
                "full_name": full_factory_str,  # 完整行名称（如"鳕峰（新地址），鳕峰沥水垫"）
                "factories": factories  # 组内厂家列表
            })
            all_factory_set.update(factories)

        logger.info(f"✅ 厂家映射表校验通过，共解析出 {len(factory_group_info)} 组厂家")

        # ===================== 步骤2：构建厂家→完整行名称的映射 =====================
        factory_to_full_name: Dict[str, str] = {}
        for group in factory_group_info:
            full_name = group["full_name"]
            for f in group["factories"]:
                factory_to_full_name[f] = full_name

        # ===================== 步骤3：读取并融合成本表 =====================
        # 读取成本表
        cost_df = pd.read_excel(cost_file, header=0)
        
        # 兼容旧版成本表（只有"成本"列）和新版成本表（有"jit成本"和"vmi成本"列）
        if "成本" in cost_df.columns:
            # 旧版成本表：将"成本"列拆分为"jit成本"和"vmi成本"
            cost_df[jit_cost_col] = cost_df["成本"]
            cost_df[vmi_cost_col] = cost_df["成本"]
            # 删除旧的"成本"列，确保只使用jit成本和vmi成本
            cost_df = cost_df.drop(columns=['成本'])
            logger.info("📌 检测到旧版成本表，已将'成本'列拆分为'jit成本'和'vmi成本'，并删除原'成本'列")
        
        # 校验必要列
        required_cols = [factory_col, skc_col, sku_col, jit_cost_col, vmi_cost_col]
        missing_cols = [col for col in required_cols if col not in cost_df.columns]
        if missing_cols:
            raise ValueError(f"成本表缺失必要列：{missing_cols}")

        # 去重空值行
        cost_df = cost_df.dropna(subset=[factory_col, skc_col, sku_col]).reset_index(drop=True)
        if len(cost_df) == 0:
            raise ValueError("成本表无有效数据！")

        # 核心修正：替换厂家名称为【完整行名称】
        cost_df['厂家名称_统一'] = cost_df[factory_col].astype(str).str.strip().map(factory_to_full_name)

        # 处理未匹配到的厂家（保留原名称）
        cost_df['厂家名称_统一'] = cost_df['厂家名称_统一'].fillna(cost_df[factory_col])

        # 按【完整厂家+SKC货号+SKU属性】去重，保留第一条
        merge_key = ['厂家名称_统一', skc_col, sku_col]
        merged_cost_df = cost_df.drop_duplicates(subset=merge_key, keep='first').reset_index(drop=True)

        # 替换原厂家名称列为完整行名称，删除临时列
        merged_cost_df[factory_col] = merged_cost_df['厂家名称_统一']
        merged_cost_df = merged_cost_df.drop(columns=['厂家名称_统一'])

        # ===================== 步骤4：保存融合后的成本表 =====================
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        merged_cost_df.to_excel(output_file, index=False)

        logger.success(f"✅ 成本表融合完成！")
        logger.info(f"📁 原成本表行数：{len(cost_df)}")
        logger.info(f"📁 融合后行数：{len(merged_cost_df)}")
        logger.info(f"💾 输出路径：{output_file}")

        return {
            "code": 1,
            "msg": "厂家映射表校验通过，成本表融合成功",
            "data": {
                "factory_group_count": len(factory_group_info),
                "original_cost_rows": len(cost_df),
                "merged_cost_rows": len(merged_cost_df),
                "output_path": output_file
            }
        }

    except Exception as e:
        logger.error(f"❌ 执行失败：{str(e)}", exc_info=True)
        return {
            "code": -1,
            "msg": f"执行失败：{str(e)}",
            "data": None
        }


def merge_cost_with_improve_table(
        cost_table_path: str,
        improve_table_path: str,
        output_path: str,
        key_cols=None
) -> dict:
    """
    将成本完善表中的数据补充/更新到计算成本表中（核心新增逻辑）
    :param cost_table_path: 计算成本表路径（配置文件_成本/计算成本/MPM_成本.xlsx）
    :param improve_table_path: 成本完善表路径（配置文件_结算导出/店铺/月份/成本完善表_月份.xlsx）
    :param output_path: 融合后的输出路径（建议覆盖计算成本表）
    :param key_cols: 匹配关键字段（厂家+SKC+SKU）
    :return: 融合结果
    """
    if key_cols is None:
        key_cols = ["厂家名称", "SKC货号", "SKU属性"]
    try:
        # 1. 读取计算成本表（若不存在则创建空表）
        if os.path.exists(cost_table_path):
            cost_df = pd.read_excel(cost_table_path, header=0)
            logger.info(f"📌 读取计算成本表：{cost_table_path}（行数：{len(cost_df)}）")
        else:
            # 新版成本表结构：厂家名称, SKC货号, SKU属性, jit成本, vmi成本
            cost_df = pd.DataFrame(columns=key_cols + ["jit成本", "vmi成本"])
            logger.warning(f"⚠️ 计算成本表不存在，创建空表：{cost_table_path}")

        # 2. 读取成本完善表（若不存在则直接返回）
        if not os.path.exists(improve_table_path):
            logger.info(f"⚠️ 成本完善表不存在：{improve_table_path}，跳过融合")
            return {"code": 1, "msg": "成本完善表不存在，跳过融合", "data": None}

        improve_df = pd.read_excel(improve_table_path, header=0)
        logger.info(f"📌 读取成本完善表：{improve_table_path}（行数：{len(improve_df)}）")

        # 兼容旧版成本完善表（只有"成本"列）和新版成本完善表（有"jit成本"和"vmi成本"列）
        if "成本" in improve_df.columns and "jit成本" not in improve_df.columns:
            # 旧版成本完善表：将"成本"列拆分为"jit成本"和"vmi成本"
            improve_df["jit成本"] = improve_df["成本"]
            improve_df["vmi成本"] = improve_df["成本"]
            # 删除旧的"成本"列，确保只使用jit成本和vmi成本
            improve_df = improve_df.drop(columns=['成本'])
            logger.info("📌 检测到旧版成本完善表，已将'成本'列拆分为'jit成本'和'vmi成本'，并删除原'成本'列")

        # 3. 数据预处理（去重+过滤空值）
        improve_df = improve_df.dropna(subset=key_cols).drop_duplicates(subset=key_cols, keep='last')
        cost_df = cost_df.dropna(subset=key_cols).drop_duplicates(subset=key_cols, keep='last')

        # 4. 融合逻辑：
        # - 成本完善表中有成本的行：更新计算成本表对应行
        # - 成本完善表中无成本的行：新增到计算成本表（留空成本，等待手动配置）
        # 4.1 先合并所有数据
        merged_df = pd.concat([cost_df, improve_df], ignore_index=True)
        # 4.2 去重：保留最后一条（成本完善表优先覆盖计算成本表）
        merged_df = merged_df.drop_duplicates(subset=key_cols, keep='last')
        # 4.3 重置索引
        merged_df = merged_df.reset_index(drop=True)

        # 5. 保存融合后的计算成本表
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        merged_df.to_excel(output_path, index=False)
        logger.success(f"✅ 成本完善表融合完成：")
        logger.info(f"   - 原计算成本表行数：{len(cost_df)}")
        logger.info(f"   - 成本完善表行数：{len(improve_df)}")
        logger.info(f"   - 融合后行数：{len(merged_df)}")
        logger.info(f"   - 输出路径：{output_path}")

        return {
            "code": 1,
            "msg": "成本完善表与计算成本表融合成功",
            "data": {
                "original_cost_rows": len(cost_df),
                "improve_rows": len(improve_df),
                "merged_rows": len(merged_df),
                "output_path": output_path
            }
        }

    except Exception as e:
        logger.error(f"❌ 融合成本完善表失败：{str(e)}", exc_info=True)
        return {"code": -1, "msg": f"融合失败：{str(e)}", "data": None}




def is_file_locked_optimized(file_path: str, timeout: float = 3.0) -> Tuple[bool, Optional[list[str]]]:
    """
    优化版文件占用检查（带超时，跳过系统进程）
    :param file_path: 待检查文件路径
    :param timeout: 遍历超时时间（秒）
    :return: (是否被占用, 占用进程列表)
    """
    locked = False
    process_names = []
    start_time = time.time()

    try:
        # 只遍历用户进程（排除系统进程），减少遍历量
        for proc in psutil.process_iter(['pid', 'name', 'username', 'open_files']):
            # 超时保护：超过3秒直接退出检查
            if time.time() - start_time > timeout:
                logger.warning(f"⚠️ 文件占用检查超时（{timeout}秒），跳过剩余进程")
                break

            try:
                # 跳过系统进程/无权限进程
                if proc.info['username'] is None:
                    continue

                open_files = proc.info['open_files']
                if not open_files:
                    continue

                # 检查是否占用目标文件
                for open_file in open_files:
                    if open_file.path and os.path.abspath(open_file.path) == file_path:
                        locked = True
                        process_names.append(f"{proc.info['name']}(PID:{proc.info['pid']})")
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except Exception as e:
                logger.debug(f"🔍 检查进程失败：{e}")
                continue
    except Exception as e:
        logger.warning(f"⚠️ 文件占用检查异常：{str(e)}")

    return locked, process_names


def safe_delete_file(
        file_path: str,
        force_delete: bool = False,  # 强制删除（即使文件被占用）
        skip_lock_check: bool = True  # 跳过耗时的文件占用检查
) -> dict:
    """
    优化版安全删除文件：解决卡住问题
    :param file_path: 待删除文件路径
    :param force_delete: 是否强制删除
    :param skip_lock_check: 是否跳过文件占用检查（优先保证删除速度）
    :return: 删除结果字典
    """
    # 标准化路径
    file_path = os.path.abspath(file_path)
    logger.info(f"📌 开始处理文件删除：{file_path}")

    # 步骤1：基础检查（文件是否存在/是否为文件）
    if not os.path.exists(file_path):
        logger.warning(f"⚠️ 文件不存在：{file_path}")
        return {
            "code": 1,
            "msg": "文件不存在，无需删除",
            "data": {"file_path": file_path}
        }

    if not os.path.isfile(file_path):
        logger.error(f"❌ 目标路径不是文件：{file_path}")
        return {
            "code": -1,
            "msg": "目标路径不是文件，无法删除",
            "data": {"file_path": file_path}
        }

    # 步骤2：可选的文件占用检查（不再阻塞删除）
    is_locked = False
    lock_processes = []
    if not skip_lock_check:
        logger.info("🔍 开始检查文件占用状态（超时3秒）...")
        is_locked, lock_processes = is_file_locked_optimized(file_path, timeout=3.0)
        if is_locked:
            logger.warning(f"⚠️ 文件被占用：{file_path} | 占用进程：{lock_processes}")
            if not force_delete:
                logger.error(f"❌ 文件被占用且未开启强制删除，终止操作")
                return {
                    "code": -1,
                    "msg": f"文件被占用，无法删除（占用进程：{lock_processes}）",
                    "data": {"file_path": file_path, "lock_processes": lock_processes}
                }
            logger.info("🔧 开启强制删除模式...")

    # 步骤3：快速权限检查（简化版）
    try:
        # 仅检查文件是否可写（无需创建临时文件）
        if not os.access(file_path, os.W_OK):
            raise PermissionError("无文件写入/删除权限")
        logger.info("✅ 验证通过：拥有文件删除权限")
    except PermissionError:
        logger.error(f"❌ 无权限删除文件：{file_path}（需要管理员权限）")
        return {
            "code": -1,
            "msg": "无权限删除文件，请以管理员身份运行",
            "data": {"file_path": file_path}
        }
    except Exception as e:
        logger.warning(f"⚠️ 权限检查警告：{str(e)}（继续尝试删除）")

    # 步骤4：快速删除（核心优化）
    try:
        # Windows/Linux 通用强制删除逻辑
        if sys.platform == "win32":
            # Windows 使用powershell快速删除（比cmd更稳定）
            subprocess.run(
                ['powershell', '-Command', f"Remove-Item -Path '{file_path}' -Force -ErrorAction SilentlyContinue"],
                timeout=5,
                capture_output=True,
                text=True
            )
        else:
            # Linux/macOS
            subprocess.run(['rm', '-f', file_path], timeout=5, capture_output=True)

        # 验证删除结果
        if not os.path.exists(file_path):
            logger.success(f"✅ 文件删除成功：{file_path}")
            return {
                "code": 1,
                "msg": "文件删除成功",
                "data": {"file_path": file_path, "force_delete": force_delete}
            }
        else:
            logger.error(f"❌ 执行删除操作后，文件仍存在：{file_path}")
            return {
                "code": -1,
                "msg": "执行删除操作后文件仍存在",
                "data": {"file_path": file_path}
            }

    except subprocess.TimeoutExpired:
        logger.error(f"❌ 删除操作超时（5秒）：{file_path}")
        return {
            "code": -1,
            "msg": "删除操作超时",
            "data": {"file_path": file_path}
        }
    except Exception as e:
        logger.error(f"❌ 文件删除失败：{str(e)}", exc_info=True)
        return {
            "code": -1,
            "msg": f"文件删除失败：{str(e)}",
            "data": {"file_path": file_path, "error_detail": str(e)}
        }


if __name__ == '__main__':
    # 配置loguru日志（可选）
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
    )
    # 测试文件路径（请替换为你的实际路径）
    path_p = r"../../../配置文件_成本"
    FACTORY_FILE = rf"{path_p}/相同厂家配置表.xlsx"  # 厂家映射表（一列：厂家名称）
    COST_FILE = rf"{path_p}/MPM_成本.xlsx"  # 原始成本表
    OUTPUT_FILE = rf"{path_p}/计算成本/MPM_成本.xlsx"  # 输出路径

    # 执行融合
    result = validate_and_merge_cost_table(
        factory_mapping_file=FACTORY_FILE,
        cost_file=COST_FILE,
        output_file=OUTPUT_FILE
    )

    print(f"\n执行结果：{result}")


    # 单文件删除示例
    # test_file = "test_delete.txt"
    # # 创建测试文件
    # with open(test_file, 'w', encoding='utf-8') as f:
    #     f.write("test")
    #
    # # 执行删除
    # delete_result = safe_delete_file(test_file)
    # logger.info(f"删除结果：{delete_result}")

    # 批量删除示例（删除当前目录下所有txt文件）
    # batch_result = batch_delete_files(".", "*.txt")
    # logger.info(f"批量删除结果：{batch_result}")
