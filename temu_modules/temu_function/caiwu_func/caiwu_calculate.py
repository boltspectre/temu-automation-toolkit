import os
import warnings
from typing import List, Optional, Union, Any, Dict

import pandas as pd
from loguru import logger

from utils.TemuBase import get_shop_info_db

# 忽略openpyxl的默认样式警告（避免控制台冗余输出）
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl.styles.stylesheet")


def read_excel_data(
        file_path: str,
        sheet_name: Optional[Union[str, int]] = 0,
) -> pd.DataFrame:
    """
    通用Excel读取函数：读取任意Excel文件的指定工作表，返回清理后的DataFrame
    :param file_path: Excel文件路径（相对/绝对路径均可）
    :param sheet_name: 工作表名称（字符串）或索引（默认0=第一个工作表）
    :return: 清理后的DataFrame（已去除全空行、重置索引）
    :raises FileNotFoundError: 文件不存在时抛出
    :raises ValueError: 工作表不存在/读取失败时抛出
    """
    # 处理路径：相对路径转绝对路径，便于定位文件
    abs_file_path = os.path.abspath(file_path)
    # 提前定义file_name变量，避免在异常处理中使用未定义的变量
    file_name = os.path.basename(abs_file_path)
    
    if not os.path.exists(abs_file_path):
        raise FileNotFoundError(f"文件不存在：{abs_file_path}（输入路径：{file_path}）")

    try:
        # 读取Excel（兼容.xlsx格式，支持跳过空行）
        df = pd.read_excel(
            io=abs_file_path,
            sheet_name=sheet_name,
            engine="openpyxl",
        )
        # 清理数据：去除全空行、重置索引
        df_clean = df.dropna(how="all").reset_index(drop=True)

        # 日志输出：仅展示关键信息，不耦合业务
        print(f"✅ 读取成功：{file_name}")
        # print(f"   - 数据行数：{len(df_clean)} | 列名：{list(df_clean.columns)}")
        return df_clean

    except ValueError as e:
        # 优化工作表不存在的错误提示（显示可用工作表）
        if "Worksheet" in str(e):
            try:
                xl = pd.ExcelFile(abs_file_path, engine="openpyxl")
                raise ValueError(
                    f"工作表不存在：{sheet_name}（文件：{file_name}）\n"
                    f"可用工作表：{xl.sheet_names}"
                ) from e
            except Exception:
                raise ValueError(f"读取工作表失败：{str(e)}（文件：{file_name}）") from e
        else:
            raise ValueError(f"Excel读取失败：{str(e)}（文件：{file_name}）") from e
    except Exception as e:
        raise Exception(f"文件处理异常：{str(e)}（路径：{abs_file_path}）") from e


def get_column_unique_values(
        df: pd.DataFrame,
        target_col: str,
        sort_values: bool = True,
        drop_na: bool = True,
        where_conditions: Optional[Union[Dict[str, Any], str]] = None
) -> List[Any]:
    """
    通用列去重取值函数：筛选符合条件的行后，提取指定列的所有不同值并返回列表
    :param df: 输入DataFrame
    :param target_col: 要提取不同值的目标列名
    :param sort_values: 是否对结果列表排序（默认True）
    :param drop_na: 是否剔除空值（NaN/None，默认True）
    :param where_conditions: 筛选条件，支持两种格式：
        1. 字典格式（等值条件，自动AND）：{"列1": 值1, "列2": 值2} → 列1=值1 and 列2=值2
        2. 字符串格式（复杂条件）："列1 > 0 and 列2 == '人民币'" 或 "列3 != '退款' or 列4 < 100"
    :return: 目标列的所有不同值组成的列表
    :raises KeyError: 目标列/条件列不存在时抛出
    :raises ValueError: 条件解析失败时抛出
    """
    # 1. 条件过滤（和calculate_column_sum保持一致的过滤逻辑）
    df_filtered = df.copy()
    if where_conditions is not None:
        # 字典格式（等值AND条件）
        if isinstance(where_conditions, dict):
            missing_cols = [col for col in where_conditions.keys() if col not in df_filtered.columns]
            if missing_cols:
                raise KeyError(f"WHERE条件中的列不存在：{missing_cols}\n当前列名：{list(df_filtered.columns)}")
            for col, value in where_conditions.items():
                df_filtered = df_filtered[df_filtered[col] == value]
        # 字符串格式（复杂条件）
        elif isinstance(where_conditions, str):
            try:
                mask = pd.eval(f"`{df_filtered.index.name}` in df_filtered.index and ({where_conditions})",
                               local_dict={"df_filtered": df_filtered})
                df_filtered = df_filtered[mask]
            except Exception as e:
                raise ValueError(f"WHERE条件解析失败：{where_conditions}\n错误原因：{str(e)}") from e

    # 2. 检查目标列是否存在
    if target_col not in df_filtered.columns:
        raise KeyError(f"目标列不存在：'{target_col}'\n当前列名：{list(df_filtered.columns)}")

    # 3. 提取唯一值并处理空值
    unique_vals = df_filtered[target_col].unique()
    if drop_na:
        # 剔除NaN/None（兼容不同数据类型的空值）
        unique_vals = [val for val in unique_vals if pd.notna(val)]

    # 4. 排序（可选）
    if sort_values and len(unique_vals) > 0:
        # 兼容数字/字符串混合排序
        try:
            unique_vals = sorted(unique_vals)
        except TypeError:
            # 混合类型无法排序时转为字符串排序
            unique_vals = sorted([str(val) for val in unique_vals])

    # 5. 转换为列表返回
    result_list = list(unique_vals)

    # 日志提示（可选）
    print(f"✅ 提取完成：列'{target_col}'共找到 {len(result_list)} 种不同值")
    # 可选：打印前10个值（避免数据过多）
    # if len(result_list) > 0:
    #     print(f"   示例值：{result_list[:10]}{'...' if len(result_list) > 10 else ''}")

    return result_list


def calculate_column_sum(
        df: pd.DataFrame,
        target_col: str,
        decimal_places: int = 2,
        unit: str = "无",
        show_invalid: bool = False,
        where_conditions: Optional[Union[Dict[str, Any], str]] = None,
        contains: bool = False
) -> float:
    """
    通用列求和函数（支持类SQL WHERE条件过滤）
    :param df: 输入DataFrame
    :param target_col: 要求和的目标列名
    :param decimal_places: 结果保留小数位数
    :param unit: 列的单位
    :param show_invalid: 是否显示无效数据
    :param where_conditions: WHERE条件，支持两种格式：
        1. 字典格式（等值条件，自动AND）：{"列1": 值1, "列2": 值2} → 列1=值1 and 列2=值2
        2. 字符串格式（复杂条件）："列1 > 0 and 列2 == '人民币'" 或 "列3 != '退款' or 列4 < 100"
    :param contains: 是否使用包含匹配（默认False，使用全等于；True时使用str.contains）
    :return: 过滤后目标列的总和
    :raises KeyError: 目标列/条件列不存在时抛出
    :raises ValueError: 条件解析失败/无有效数据时抛出
    """
    # --------------------------
    # 新增：1. 执行WHERE条件过滤
    # --------------------------
    df_filtered = df.copy()  # 复制原数据，避免修改原DataFrame
    if where_conditions is not None:
        # 情况1：字典格式（等值条件，AND逻辑）
        if isinstance(where_conditions, dict):
            # 检查条件中的列是否存在
            missing_cols = [col for col in where_conditions.keys() if col not in df_filtered.columns]
            if missing_cols:
                raise KeyError(f"WHERE条件中的列不存在：{missing_cols}\n当前列名：{list(df_filtered.columns)}")
            # 逐列过滤（AND逻辑）
            for col, value in where_conditions.items():
                if contains:
                    # 使用包含匹配
                    df_filtered = df_filtered[df_filtered[col].astype(str).str.contains(str(value), na=False)]
                else:
                    # 使用全等于
                    df_filtered = df_filtered[df_filtered[col] == value]

        # 情况2：字符串格式（复杂条件，支持>/"<"/"and"/"or"等）
        elif isinstance(where_conditions, str):
            try:
                # 使用pd.eval解析条件表达式
                mask = pd.eval(f"`{df_filtered.index.name}` in df_filtered.index and ({where_conditions})",
                               local_dict={"df_filtered": df_filtered})
                df_filtered = df_filtered[mask]
            except Exception as e:
                raise ValueError(f"WHERE条件解析失败：{where_conditions}\n错误原因：{str(e)}") from e

        # 检查过滤后是否有数据
        # if len(df_filtered) == 0:
        #     raise ValueError(f"WHERE条件过滤后无数据：{where_conditions}")
        #
        # print(f"\n🔍 WHERE条件过滤结果：")
        # print(f"   - 过滤条件：{where_conditions}")
        # print(f"   - 过滤前行数：{len(df)} | 过滤后行数：{len(df_filtered)}")

    # --------------------------
    # 原有逻辑：数据转换与无效值检测（基于过滤后的数据）
    # --------------------------
    # 1. 检查目标列是否存在
    if target_col not in df_filtered.columns:
        raise KeyError(f"目标列不存在：'{target_col}'\n当前列名：{list(df_filtered.columns)}")

    # 2. 转换数据并记录原始索引
    df_with_index = df_filtered[[target_col]].reset_index(drop=False)
    df_with_index["cleaned"] = df_with_index[target_col].astype(str).str.replace(r"[^\d.-]", "", regex=True)
    df_with_index["numeric"] = pd.to_numeric(df_with_index["cleaned"], errors="coerce")

    # 3. 统计有效/无效数据
    valid_data = df_with_index[df_with_index["numeric"].notna()]
    invalid_data = df_with_index[df_with_index["numeric"].isna()]
    valid_count = len(valid_data)
    invalid_count = len(invalid_data)

    # 4. 显示无效数据（若开启）
    if show_invalid and invalid_count > 0:
        print(f"\n❌ 发现 {invalid_count} 行无效数据（行号：过滤后数据行号，内容：原始值）：")
        for idx, row in invalid_data.iterrows():
            # 过滤后数据的行号（从1开始）
            filtered_row = row["index"] + 1
            print(f"   行{filtered_row}：原始值='{row[target_col]}' → 清理后='{row['cleaned']}'")
        if invalid_count > 10:
            print(f"   ... （剩余 {invalid_count - 10} 行无效数据未显示）")

    # 5. 检查是否有有效数值
    # if valid_count == 0:
    #     raise ValueError(f"目标列'{target_col}'无有效数值（过滤后数据中）")

    # 6. 计算总和并返回
    col_total = round(valid_data["numeric"].sum(), decimal_places)
    # print(f"\n📊 列求和结果：")
    # print(f"   - 目标列：{target_col} | 有效行数：{valid_count} | 无效行数：{invalid_count}")
    # print(f"   - 总和：{col_total} | 单位：{unit}")
    return col_total


def merge_excel_files(
        file_paths: List[str],
        sheet_name: Union[str, int] = 0,
        out_sheet_name="总表",
        output_path: Optional[str] = None,
        unique_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    通用多表去重融合函数：支持任意同结构Excel表的合并，不依赖特定列名
    :param file_paths: 待融合的Excel文件路径列表（如["file1.xlsx", "file2.xlsx"]）
    :param unique_cols: 去重依据的列名列表（如["订单号", "ID"]，None=全列去重）
    :param sheet_name: 所有表的工作表名称/索引（需统一，保证结构一致）
    :param output_path: 融合结果保存路径（None=不保存，仅返回DataFrame）
    :return: 去重后的融合DataFrame
    """
    # 1. 读取所有有效文件（跳过错误文件，保留有效数据）
    valid_data_list = []
    error_messages = []
    print(f"\n🔍 开始读取待融合文件（共{len(file_paths)}个）：")
    for idx, file in enumerate(file_paths, 1):
        try:
            df = read_excel_data(
                file_path=file,
                sheet_name=sheet_name,
            )
            valid_data_list.append({
                "file_name": os.path.basename(file),
                "data": df
            })
            print(f"   {idx}. 成功：{os.path.basename(file)}（行数：{len(df)}）")
        except Exception as e:
            # 简化错误提示，仅展示关键信息
            err_msg = str(e)[:60] + "..." if len(str(e)) > 60 else str(e)
            print(f"   {idx}. 失败：{os.path.basename(file)} → {err_msg}")
            error_messages.append(f"文件 {os.path.basename(file)} 读取失败：{str(e)}")

    # 检查是否有有效文件
    if not valid_data_list:
        # 创建空表
        empty_df = pd.DataFrame()
        print(f"\n📝 创建空表：无有效数据可融合")
        
        # 如果指定了输出路径，保存空表和异常日志
        if output_path:
            abs_output = os.path.abspath(output_path)
            output_dir = os.path.dirname(abs_output)
            os.makedirs(output_dir, exist_ok=True)
            
            # 保存空表
            empty_df.to_excel(abs_output, index=False, engine="openpyxl", sheet_name=out_sheet_name)
            print(f"💾 空表已保存：{abs_output}")
            
            # 保存异常日志
            error_log_path = os.path.join(output_dir, "异常.txt")
            with open(error_log_path, "w", encoding="utf-8") as f:
                f.write("📝 异常信息\n")
                f.write("="*50 + "\n")
                f.write("原因：无有效文件可融合\n")
                f.write("\n各文件错误信息：\n")
                for i, msg in enumerate(error_messages, 1):
                    f.write(f"{i}. {msg}\n")
                f.write("\n提示：请检查文件路径、格式或工作表是否正确\n")
            print(f"📄 异常日志已保存：{error_log_path}")
        
        return empty_df
    # 2. 校验所有表的结构一致性（列名、顺序完全一致）
    base_df = valid_data_list[0]["data"]
    base_file = valid_data_list[0]["file_name"]
    base_cols = base_df.columns.tolist()
    print(f"\n📋 检查表结构一致性（基准表：{base_file}）：")

    for item in valid_data_list[1:]:
        current_cols = item["data"].columns.tolist()
        if current_cols != base_cols:
            raise ValueError(
                f"表结构不一致：{item['file_name']}与{base_file}列名不匹配\n"
                f"   基准列名：{base_cols}\n"
                f"   当前列名：{current_cols}"
            )
    print(f"   ✅ 所有表结构一致（共{len(base_cols)}列）")

    # 3. 合并所有数据（纵向合并，重置索引）
    merged_df = pd.concat(
        [item["data"] for item in valid_data_list],
        axis=0,
        ignore_index=True  # 重置索引，避免原索引重复
    )
    total_before = len(merged_df)
    total_accumulate = sum(len(item["data"]) for item in valid_data_list)
    print(f"\n🔄 数据合并完成：")
    print(f"   - 各表行数累加：{total_accumulate} | 合并后行数：{total_before}")

    # 4. 去重处理（支持指定列或全列去重）
    print(f"\n🗑️  开始去重（去重依据：{unique_cols if unique_cols else '全列'}）：")
    # 检查去重列是否存在（若指定了unique_cols）
    if unique_cols:
        missing_cols = [col for col in unique_cols if col not in merged_df.columns]
        if missing_cols:
            raise ValueError(
                f"去重列不存在：{missing_cols}\n"
                f"当前表所有列名：{list(merged_df.columns)}"
            )
        # 按指定列去重（保留首次出现的行）
        merged_df = merged_df.drop_duplicates(
            subset=unique_cols,
            keep="first",
            inplace=False
        )
    else:
        # 全列去重（所有列值完全相同视为重复）
        merged_df = merged_df.drop_duplicates(keep="first", inplace=False)

    # 5. 输出去重结果
    duplicate_count = total_before - len(merged_df)
    print(f"   - 去重前行数：{total_before} | 去重后行数：{len(merged_df)}")
    print(f"   - 删除重复行数：{duplicate_count}")

    # 6. 保存结果（可选，自动创建目录）
    if output_path:
        abs_output = os.path.abspath(output_path)
        output_dir = os.path.dirname(abs_output)
        # 自动创建父目录（避免路径不存在报错）
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        # 保存Excel（不保留索引，自定义工作表名）
        merged_df.to_excel(
            abs_output,
            index=False,
            engine="openpyxl",
            sheet_name=out_sheet_name
        )
        print(f"\n💾 融合结果已保存：{abs_output}")

    return merged_df


def start_merge_excel(merge_file_list: list[str], sheet_name: int | str, out_sheet_name="总表",
                      output_path: str = "caiwu_func/caiwu/融合结果_最终版.xlsx", unique_cols: list[str] = None):
    print("\n\n" + "=" * 60)
    print("🔗 通用多表去重融合")
    print("=" * 60)
    try:
        # 调用多表融合函数
        merged_result = merge_excel_files(
            file_paths=merge_file_list,
            output_path=output_path,
            out_sheet_name=out_sheet_name,
            sheet_name=sheet_name,
            unique_cols=unique_cols
        )

        # 验证融合结果：去重是否完整
        print(f"\n✅ 融合完成！融合结果统计：")
        print(f"   融合后总行数：{len(merged_result)}")
        # 再次验证组合键是否无重复

        print(f"\n💾 最终融合文件已保存：{output_path}")

    except Exception as e:
        print(f"\n❌ 多表融合失败：{str(e)}")


def merge_all_excel_file(uid, months_list):
    # 按地区表融合
    shop_info = get_shop_info_db(uid)
    regions = ["eu", "us", "global"]
    for month in months_list:
        # 检查哪些文件实际存在
        merge_file_list = []
        for region in regions:
            file_path = f"配置文件_结算导出/{shop_info['shop_abbr']}/{month}/导出原表_{region}_{month}.xlsx"
            if os.path.exists(file_path):
                merge_file_list.append(file_path)
            else:
                logger.warning(f"文件不存在，跳过: {file_path}")

        # 如果没有文件存在，跳过此月份
        if not merge_file_list:
            logger.warning(f"月份 {month} 没有任何区域文件存在，跳过融合")
            continue

        for mode in [1, 2]:
            if mode == 1:
                out_sheet_name = "交易结算总表"
                sheet_name = "交易结算"
                output_path = f"配置文件_结算导出/{shop_info['shop_abbr']}/{month}/交易结算总表_{month}.xlsx"
            else:
                out_sheet_name = "履约保障售后问题总表"
                sheet_name = "消费者及履约保障-售后问题"
                output_path = f"配置文件_结算导出/{shop_info['shop_abbr']}/{month}/履约保障售后问题总表_{month}.xlsx"

            start_merge_excel(merge_file_list, out_sheet_name=out_sheet_name, sheet_name=sheet_name,
                              output_path=output_path, unique_cols=None)

    logger.success(f"✅ 月份 {months_list} 多表融合完成")


def update_rows_where(
        df: pd.DataFrame,
        target_col: str,
        new_value,
        where_conditions: dict,
        create_if_not_exists: bool = False
) -> pd.DataFrame:
    """
    根据指定的条件筛选DataFrame中的行，并为这些行的指定列更新新值。
    如果目标列不存在，可以选择自动创建它。
    此函数不会修改原始DataFrame，而是返回一个更新后的副本。

    :param df: 要操作的Pandas DataFrame。
    :param target_col: 需要更新或创建的目标列名。
    :param new_value: 要插入的新值。
    :param where_conditions: 筛选条件的字典。
    :param create_if_not_exists: 如果为True，当目标列不存在时会自动创建。默认为False。
    :return: 更新后的新DataFrame。
    """
    # 1. 输入验证 (只验证 where_conditions 中的列)
    for col in where_conditions.keys():
        if col not in df.columns:
            raise ValueError(f"错误：条件列 '{col}' 不存在于DataFrame中。")

    # 2. 创建DataFrame的副本
    df_copy = df.copy()

    # 3. 检查目标列是否存在，如果不存在且需要创建
    if target_col not in df_copy.columns:
        if create_if_not_exists:
            print(f"信息：目标列 '{target_col}' 不存在，将自动创建为字符串类型。")

            # --- 核心修改在这里 ---
            # 使用 pd.Series 创建一个空的字符串列，而不是用 np.nan
            # dtype='string' 是现代Pandas中推荐的字符串类型
            df_copy[target_col] = pd.Series(dtype='string')
        else:
            raise ValueError(f"错误：目标列 '{target_col}' 不存在于DataFrame中。")

    # 4. 构建筛选条件的掩码 (mask)
    mask = pd.Series([True] * len(df_copy), index=df_copy.index)
    for col, value in where_conditions.items():
        condition = (df_copy[col] == value)
        mask = mask & condition

    if not mask.any():
        print(f"警告：没有找到满足条件 {where_conditions} 的行，未进行任何更新。")
        return df_copy

    # 5. 使用掩码更新目标列的值
    df_copy.loc[mask, target_col] = new_value

    print(f"成功找到 {mask.sum()} 行满足条件 {where_conditions}，并已更新列 '{target_col}' 的值。")

    return df_copy


def start_exctract_money_excel(excel_path, total_excel_path, shouhou_excel_path, month: str = None):
    try:
        # 结算总表
        df = read_excel_data(file_path=excel_path, sheet_name=0)
        # 结算总表履约售后问题分页
        履约售后问题总表 = read_excel_data(file_path=shouhou_excel_path, sheet_name=0)
        # 卖家中心表
        total = read_excel_data(file_path=total_excel_path, sheet_name=0)
        # 验证完整性
        key_cols = ["订单编号", "数量", "金额", "交易类型", "币种", "备货单类型"]
        exist_cols = [col for col in key_cols if col in df.columns]
        missing_cols = [col for col in key_cols if col not in df.columns]
        # print(f"\n🔍 关键列存在性：")
        # print(f"✅ 存在：{exist_cols}")
        if missing_cols:
            print(f"❌ 缺失：{missing_cols}")
        else:
            print(f"✅ 所有关键列均存在！")

        # 验证完整性
        key_cols = ["财务时间", "财务类型", "收支金额", "币种", "备注"]
        exist_cols = [col for col in key_cols if col in total.columns]
        missing_cols = [col for col in key_cols if col not in total.columns]

        总销量 = calculate_column_sum(
            df=df,
            target_col="数量",
            unit="件",
            show_invalid=True,
            where_conditions={"交易类型": "销售回款", "币种": "CNY"}
        )

        JIT销量 = calculate_column_sum(
            df=df,
            target_col="数量",
            unit="件",
            show_invalid=True,
            where_conditions={"交易类型": "销售回款", "币种": "CNY", "备货单类型": "JIT"}
        )

        备货销量 = calculate_column_sum(
            df=df,
            target_col="数量",
            unit="件",
            show_invalid=True,
            where_conditions={"交易类型": "销售回款", "币种": "CNY", "备货单类型": "VMI"}
        )

        结算收入金额 = calculate_column_sum(
            df=df,
            target_col="金额",
            unit="元",
            show_invalid=True,
            where_conditions={"交易类型": "销售回款", "币种": "CNY"}
        )

        平台补贴金额 = calculate_column_sum(
            df=df,
            target_col="金额",
            unit="元",
            show_invalid=True,
            where_conditions={"交易类型": "非商责补贴", "币种": "CNY"}
        )

        退货金额 = calculate_column_sum(
            df=df,
            target_col="金额",
            unit="元",
            show_invalid=True,
            where_conditions={"交易类型": "销售冲回", "币种": "CNY"}
        )

        仓储综合服务费 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"备注": "仓储综合服务费", "币种": "CNY"}
        )

        EPR费用 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"备注": "EPR", "币种": "CNY"},
            contains=True
        )

        # 分表的第二页 name = 消费者履约 赔付金额列的和
        履约售后问题金额 = -calculate_column_sum(
            df=履约售后问题总表,
            target_col="赔付金额",
            unit="元",
            show_invalid=True,
            where_conditions={"币种": "CNY"}
        )

        # 下表
        卖家收入金额 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "结算", "币种": "CNY"}
        )

        支出金额 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "币种": "CNY"}
        )

        提现 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "提现", "币种": "CNY"}
        )

        消费者及履约保障_售后问题 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "备注": "消费者及履约保障-售后问题", "币种": "CNY"}
        )

        仓储物流服务费 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "备注": "仓储综合服务费", "币种": "CNY"}
        )

        发货履约保障_缺货 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "备注": "发货履约保障-缺货", "币种": "CNY"}
        )

        商品品质保障_质量问题 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "备注": "商品品质保障-质量问题", "币种": "CNY"}
        )

        发货履约保_延迟到货 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "备注": "发货履约保障-延迟到货", "币种": "CNY"}
        )

        商品品质保障_质量问题_JIT商品 = calculate_column_sum(
            df=total,
            target_col="收支金额",
            unit="元",
            show_invalid=True,
            where_conditions={"账务类型": "支出", "备注": "商品品质保障-质量问题（JIT商品）", "币种": "CNY"}
        )

        履约罚款 = round(支出金额 - 消费者及履约保障_售后问题 - 仓储物流服务费 - EPR费用, 2)

        成本金额 = calculate_column_sum(
            df=df,
            target_col="订单总成本",
            unit="元",
            show_invalid=True,
            where_conditions={"交易类型": "销售回款", "币种": "CNY"}
        )
        # ====================================================================

        # 成本是支出，所以在计算利润时应为负数
        成本金额 = -abs(成本金额) if 成本金额 > 0 else 成本金额

        结算总表利润 = round(结算收入金额 + 平台补贴金额 + 成本金额 + 退货金额 + 履约售后问题金额 + 履约罚款 + 0 + 仓储综合服务费 + EPR费用, 2)
        利润率 = round(结算总表利润 / 结算收入金额, 2)
        每单利润 = round(结算总表利润 / 总销量, 2)
        退货金额占比 = round(abs(退货金额) / 结算收入金额, 2)
        售后问题金额占比 = round(abs(履约售后问题金额) / 结算收入金额, 2)

        履约罚款率 = round(abs(履约罚款) / 结算收入金额, 2)

        售后履约问题率总计 = 退货金额占比 + 售后问题金额占比 + 履约罚款率

        logger.success(f"✅ 表格数据 {excel_path} 计算完成")

        # 总销量
        # JIT销量
        # 备货销量
        # 结算收入金额
        # 平台补贴金额
        # 成本金额
        # 退货金额
        # 履约售后问题
        #
        # 履约罚款 + 其他
        # 仓储物流服务费
        # 结算表格利润
        # 利润率
        # 每单利润
        #
        # 售后履约问题总计：sum
        # 退货率
        # 售后问题率
        # 履约罚款 + 其他率

        settle_result = {
            # 上表
            "总销量": 总销量,
            "JIT销量": JIT销量,
            "备货销量": 备货销量,
            "结算收入金额": 结算收入金额,
            "平台补贴金额": 平台补贴金额,
            "成本金额": 成本金额,
            "退货金额": 退货金额,
            "履约售后问题金额": 履约售后问题金额,
            "仓储综合服务费": 仓储综合服务费,
            "EPR费用": EPR费用,
            "履约罚款": 履约罚款,
            "其他（留空待填）": 0,

            "结算总表利润": 结算总表利润,
            "利润率": 利润率,
            "每单利润": 每单利润,
            "售后履约问题率总计": 售后履约问题率总计,
            "退货金额占比": 退货金额占比,
            "售后问题金额占比": 售后问题金额占比,
            "履约罚款率": 履约罚款率,
        }

        seller_flow_result = {
            # 下表
            "卖家收入金额": 卖家收入金额,
            "支出金额": 支出金额,
            # "仓储综合服务费": 仓储综合服务费,
            "消费者及履约保障-售后问题": 消费者及履约保障_售后问题,
            "EPR费用": EPR费用,
            "发货履约保障-缺货": 发货履约保障_缺货,
            "发货履约保-延迟到货": 发货履约保_延迟到货,
            "商品品质保障-质量问题-JIT商品": 商品品质保障_质量问题_JIT商品,
            "商品品质保障-质量问题": 商品品质保障_质量问题,
            "提现": 提现,
        }

        SKC货号 = get_column_unique_values(
            df=df,
            target_col="SKC货号",
            sort_values=True
        )
        # print(f"SKC货号：{SKC货号}")

        skc_data_list = []
        for skc in SKC货号:
            # 从交易结算总表获取类目名
            skc_类目名 = df[df["SKC货号"] == skc]["类目名"].unique()
            skc_类目名 = skc_类目名[0] if len(skc_类目名) > 0 else "未知类目"
            
            # 总销量
            # JIT销量
            # 备货销量
            # 收入金额
            # 平台补贴金额

            # 成本金额
            # 退货金额
            # 履约售后问题

            # 结算表格利润
            # 利润率
            # 每单利润
            # 退货率
            # 售后问题率

            skc_总销量 = calculate_column_sum(
                df=df,
                target_col="数量",
                unit="件",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "销售回款", "币种": "CNY"}
            )

            skc_JIT销量 = calculate_column_sum(
                df=df,
                target_col="数量",
                unit="件",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "销售回款", "币种": "CNY", "备货单类型": "JIT"}
            )

            skc_备货销量 = calculate_column_sum(
                df=df,
                target_col="数量",
                unit="件",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "销售回款", "币种": "CNY", "备货单类型": "VMI"}
            )

            skc_结算收入金额 = calculate_column_sum(
                df=df,
                target_col="金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "销售回款", "币种": "CNY"}
            )

            skc_平台补贴金额 = calculate_column_sum(
                df=df,
                target_col="金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "非商责补贴", "币种": "CNY"}
            )

            skc_退货金额 = calculate_column_sum(
                df=df,
                target_col="金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "销售冲回", "币种": "CNY"}
            )

            # record_skc_to_table(uid, months_list)
            # 这里可以用新函数了
            # 分表的第二页 name = 消费者履约 赔付金额列的和
            skc_履约售后问题金额 = -calculate_column_sum(
                df=履约售后问题总表,
                target_col="赔付金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "币种": "CNY"}
            )

            skc_成本金额 = calculate_column_sum(
                df=df,
                target_col="订单总成本",
                unit="元",
                show_invalid=True,
                where_conditions={"SKC货号": skc, "交易类型": "销售回款", "币种": "CNY"}
            )

            # 成本是支出，所以在计算利润时应为负数
            skc_成本金额 = -abs(skc_成本金额) if skc_成本金额 > 0 else skc_成本金额

            skc_结算总表利润 = round(
                skc_结算收入金额 + skc_平台补贴金额 + skc_成本金额 + skc_退货金额 + skc_履约售后问题金额,
                2)

            if skc_结算收入金额 == 0:
                skc_利润率 = 0
                skc_退货金额占比 = 0
                skc_售后问题金额占比 = 0
            else:
                skc_利润率 = round(skc_结算总表利润 / skc_结算收入金额, 2)
                skc_退货金额占比 = round(abs(skc_退货金额) / skc_结算收入金额, 2)
                skc_售后问题金额占比 = round(abs(skc_履约售后问题金额) / skc_结算收入金额, 2)

            if skc_总销量 == 0:
                skc_每单利润 = 0
            else:
                skc_每单利润 = round(skc_结算总表利润 / skc_总销量, 2)

            # 看看计算逻辑
            # 结算表格利润
            # 利润率
            # 每单利润
            # 退货率
            # 售后问题率

            skc_data = {
                skc: {
                    "类目名": skc_类目名,
                    "总销量": skc_总销量,
                    "JIT销量": skc_JIT销量,
                    "备货销量": skc_备货销量,
                    "结算收入金额": skc_结算收入金额,
                    "平台补贴金额": skc_平台补贴金额,
                    "成本金额": skc_成本金额,
                    "退货金额": skc_退货金额,
                    "履约售后问题金额": skc_履约售后问题金额,
                    "结算总表利润": skc_结算总表利润,
                    "利润率": skc_利润率,
                    "每单利润": skc_每单利润,
                    "退货金额占比": skc_退货金额占比,
                    "售后问题金额占比": skc_售后问题金额占比,
                    "售后履约问题率总计": 0
                }
            }

            skc_data_list.append(skc_data)

        # SKU数据计算
        SKU_ID = get_column_unique_values(
            df=df,
            target_col="SKU ID",
            sort_values=True
        )
        
        sku_data_list = []
        for sku in SKU_ID:
            sku_skc = df[df["SKU ID"] == sku]["SKC货号"].unique()
            sku_skc = sku_skc[0] if len(sku_skc) > 0 else "未知SKC"
            sku_类目名 = df[df["SKU ID"] == sku]["类目名"].unique()
            sku_类目名 = sku_类目名[0] if len(sku_类目名) > 0 else "未知类目"
            
            sku_总销量 = calculate_column_sum(
                df=df,
                target_col="数量",
                unit="件",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "销售回款", "币种": "CNY"}
            )
            
            sku_JIT销量 = calculate_column_sum(
                df=df,
                target_col="数量",
                unit="件",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "销售回款", "币种": "CNY", "备货单类型": "JIT"}
            )
            
            sku_备货销量 = calculate_column_sum(
                df=df,
                target_col="数量",
                unit="件",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "销售回款", "币种": "CNY", "备货单类型": "VMI"}
            )
            
            sku_结算收入金额 = calculate_column_sum(
                df=df,
                target_col="金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "销售回款", "币种": "CNY"}
            )
            
            sku_平台补贴金额 = calculate_column_sum(
                df=df,
                target_col="金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "非商责补贴", "币种": "CNY"}
            )
            
            sku_退货金额 = calculate_column_sum(
                df=df,
                target_col="金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "销售冲回", "币种": "CNY"}
            )
            
            sku_履约售后问题金额 = -calculate_column_sum(
                df=履约售后问题总表,
                target_col="赔付金额",
                unit="元",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "币种": "CNY"}
            )
            
            sku_成本金额 = calculate_column_sum(
                df=df,
                target_col="订单总成本",
                unit="元",
                show_invalid=True,
                where_conditions={"SKU ID": sku, "交易类型": "销售回款", "币种": "CNY"}
            )
            
            sku_成本金额 = -abs(sku_成本金额) if sku_成本金额 > 0 else sku_成本金额
            
            sku_结算总表利润 = round(
                sku_结算收入金额 + sku_平台补贴金额 + sku_成本金额 + sku_退货金额 + sku_履约售后问题金额,
                2)
            
            if sku_结算收入金额 == 0:
                sku_利润率 = 0
                sku_退货金额占比 = 0
                sku_售后问题金额占比 = 0
            else:
                sku_利润率 = round(sku_结算总表利润 / sku_结算收入金额, 2)
                sku_退货金额占比 = round(abs(sku_退货金额) / sku_结算收入金额, 2)
                sku_售后问题金额占比 = round(abs(sku_履约售后问题金额) / sku_结算收入金额, 2)
            
            if sku_总销量 == 0:
                sku_每单利润 = 0
            else:
                sku_每单利润 = round(sku_结算总表利润 / sku_总销量, 2)
            
            sku_data = {
                sku: {
                    "SKC货号": sku_skc,
                    "类目名": sku_类目名,
                    "总销量": sku_总销量,
                    "JIT销量": sku_JIT销量,
                    "备货销量": sku_备货销量,
                    "结算收入金额": sku_结算收入金额,
                    "平台补贴金额": sku_平台补贴金额,
                    "成本金额": sku_成本金额,
                    "退货金额": sku_退货金额,
                    "履约售后问题金额": sku_履约售后问题金额,
                    "结算总表利润": sku_结算总表利润,
                    "利润率": sku_利润率,
                    "每单利润": sku_每单利润,
                    "退货金额占比": sku_退货金额占比,
                    "售后问题金额占比": sku_售后问题金额占比,
                    "售后履约问题率总计": 0
                }
            }
            
            sku_data_list.append(sku_data)

        result = {month: {
            "结算总表数据": settle_result,
            "平台流水-卖家中心": seller_flow_result,
            "skc": skc_data_list,
            "sku": sku_data_list
        }
        }
        # print("result:", result)

        return result




    # skc_data = {
    #     "SGND(70%)": {
    #         "2025.10": {
    #             "总销量": 623.7,
    #             "JIT销量": 439.6,
    #             "收入金额": 6058.51,
    #             "退货金额": -438.63,
    #             "利润率": 0.90
    #         }
    #     },
    #     "SXF(30%)": {
    #         "2025.10": {
    #             "总销量": 267.3,
    #             "JIT销量": 188.4,
    #             "收入金额": 2596.51,
    #             "退货金额": -187.98,
    #             "利润率": 0.90
    #         }
    #     },
    #     "新增SKC(10%)": {
    #         "2025.10": {"总销量": 89.1, "收入金额": 865.50}
    #     }
    # }
    # skc
    # 总销量
    # JIT销量
    # 备货销量
    # 收入金额
    # 平台补贴金额
    # 成本金额
    # 退货金额
    # 履约售后问题
    # 结算表格利润
    # 利润率
    # 每单利润
    # 退货率
    # 售后问题率

    # 卖家收入金额
    # 支出金额
    # 仓储综合服务费
    # "消费者及履约保障
    # -售后问题"
    # 发货履约保障-缺货
    # "商品品质保障
    # -质量问题"
    # "发货履约保障
    # -延迟到货"
    # 商品品质保障-质量问题（JIT商品）
    # 提现

    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")


if __name__ == "__main__":
    # 融合月份下地区表
    uid = ""
    months_list = ["2025.10", "2025.2", "2025.11"]
    merge_all_excel_file(uid, months_list)