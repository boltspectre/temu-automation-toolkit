# config/task_permission_config.py
"""
任务权限配置文件
定义不同任务类型所需的权限
"""

# 任务类型和权限的对应关系
TASK_PERMISSION_MAPPING = {
    # temu权限对应的任务类型
    "temu": [
        "upload_real_pic",  # 上传实拍图
        "modify_price",  # 核价
        "jit_govern",  # JIT维护库存
        "adjust_price",  # 调价管理
        "apply_activity",  # 报活动任务
        "expected_goods_place",  # 批量修改期望到货地点
        "purchase_delivery",  # 批量加入发货台
        "上传实拍图",  # 任务名称
        "核价",  # 任务名称
        "JIT维护库存",  # 任务名称
        "调价管理",  # 任务名称
        "报活动任务",  # 任务名称
        "批量修改期望到货地点",  # 任务名称
        "批量加入发货台"  # 任务名称
    ],
    
    # caiwu权限对应的任务类型
    "caiwu": [
        "财务报表_1",  # 导出所选月份账单
        "财务报表_2",  # 融合所选月份账单
        "财务报表_3",  # 记录所需列到总表
        "财务报表_4",  # 计算并生成财务报表
        "财务报表全流程",  # 自动生成财务报表
        "导出所选月份账单",
        "融合所选月份账单",
        "记录所需列到总表",
        "计算并生成财务报表",
        "自动生成财务报表"
    ],
    
    # spider权限对应的任务类型
    "spider": [
        "hupu_post_list",  # 虎扑帖子列表采集
        "hupu_detail_list",  # 虎扑帖子详情采集
        "hupu_score_list",  # 虎扑评分采集
        # 爬虫相关的任务类型
        # 如果有爬虫任务，可以在这里添加
    ]
}

# 反向映射：任务类型 -> 所需权限
PERMISSION_TASK_MAPPING = {}
for permission, task_types in TASK_PERMISSION_MAPPING.items():
    for task_type in task_types:
        PERMISSION_TASK_MAPPING[task_type] = permission

def get_required_permission(task_type):
    """
    获取执行指定任务类型所需的权限
    
    Args:
        task_type: 任务类型
        
    Returns:
        str: 所需权限，如果任务类型不需要特殊权限则返回None
    """
    return PERMISSION_TASK_MAPPING.get(task_type)

def check_task_permission(task_type, user_permissions):
    """
    检查用户是否有执行指定任务类型的权限
    支持中文任务名称
    
    Args:
        task_type: 任务类型（支持数字编码或中文名称）
        user_permissions: 用户权限列表
        
    Returns:
        bool: 是否有权限
    """
    required_permission = get_required_permission(task_type)
    if not required_permission:
        return True  # 不需要特殊权限的任务
    
    return required_permission in user_permissions
