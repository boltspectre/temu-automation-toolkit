import json
from typing import Union, Dict, List, Any


def load_json_file(file_path: str) -> Union[Dict[str, Any], List[Any]]:
    """
    从文件中读取JSON数据
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        解析后的JSON数据（字典或列表）
        
    Raises:
        FileNotFoundError: 如果文件不存在
        json.JSONDecodeError: 如果文件内容不是有效的JSON格式
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data


def format_json_content(content: Union[Dict[str, Any], List[Any]], indent: int = 4) -> str:
    """
    格式化JSON内容为易读的字符串
    
    Args:
        content: 要格式化的JSON内容（字典或列表）
        indent: 缩进空格数，默认为4
        
    Returns:
        格式化后的JSON字符串
    """
    return json.dumps(content, ensure_ascii=False, indent=indent)


def save_formatted_json(content: Union[Dict[str, Any], List[Any]], output_path: str, indent: int = 4) -> None:
    """
    将格式化后的JSON内容保存到文件
    
    Args:
        content: 要保存的JSON内容
        output_path: 输出文件路径
        indent: 缩进空格数，默认为4
    """
    formatted_json = format_json_content(content, indent)
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(formatted_json)


def convert_and_format_json(input_path: str, output_path: str = None, indent: int = 4) -> str:
    """
    读取JSON文件并将其格式化
    
    Args:
        input_path: 输入JSON文件路径
        output_path: 输出文件路径（可选，如果不提供则只返回格式化后的字符串）
        indent: 缩进空格数，默认为4
        
    Returns:
        格式化后的JSON字符串
    """
    # 读取JSON文件
    content = load_json_file(input_path)
    
    # 格式化JSON内容
    formatted_content = format_json_content(content, indent)
    
    # 如果提供了输出路径，则保存到文件
    if output_path:
        save_formatted_json(content, output_path, indent)
    
    return formatted_content


def validate_json_format(json_content: str) -> bool:
    """
    验证字符串是否为有效的JSON格式
    
    Args:
        json_content: 要验证的JSON字符串
        
    Returns:
        如果是有效JSON格式返回True，否则返回False
    """
    try:
        json.loads(json_content)
        return True
    except json.JSONDecodeError:
        return False


def pretty_print_json(content: Union[Dict[str, Any], List[Any]]) -> None:
    """
    直接打印格式化后的JSON内容到控制台
    
    Args:
        content: 要打印的JSON内容
    """
    formatted_content = format_json_content(content)
    print(formatted_content)


# 示例用法
if __name__ == "__main__":
    # 示例：如何使用这些函数
    # 假设我们有一个名为 'sample.json' 的文件
    formatted_json = convert_and_format_json('../test.json', 'test.json')
    print(formatted_json)