RULE_CONFIG = {
    # 特殊标签上传
    "special_tags": [
        {
            "name": "地毯标签",
            "trigger": {
                "api_source": "real_picture_list",
                "field": "rule_name",
                "condition": "contains",
                "value": "小地毯",
            },
            "action": {"type": "upload_image", "image_keyword": "小地毯"},
        },
        {
            "name": "纺织标签",
            "trigger": {
                "api_source": "real_picture_list",
                "field": "rule_name",
                "condition": "equals",
                "value": "triman标签-纺织",
            },
            "action": {"type": "upload_image", "image_keyword": "纺织标签"},
        },
    ],
    # 特殊gcc上传
    "certificate_submissions": [
        {
            "name": "浴帘套装GCC",
            "trigger": {
                "api_source": "compliance_page_query",
                "field": "cat_id",
                "condition": "equals",
                "value": 11737,
            },
            "action": {"type": "submit_cert", "file_keyword": "浴帘套装GCC"},
        },
        {
            "name": "地毯GCC",
            "trigger": {
                "api_source": "compliance_page_query",
                "field": "cat_id",
                "condition": "equals",
                "value": 12356,
            },
            "action": {"type": "submit_cert", "file_keyword": "小地毯GCC"},
        },
    ],
    # 特殊合规信息填写
    "compliance_edits": [
        {
            "name": "浴帘套装",
            "trigger": {
                "api_source": "compliance_page_query",
                "field": "cat_id",
                "condition": "equals",
                "value": 11737,
            },
            "action": {
                "type": "set_properties",
                "task_name": "其他合规信息",
                "properties": {
                    "4094": [69448],
                    "4095": [69450],
                    "4096": [69452],
                    "1000100023": [1000130000],
                    "1000100056": [1000130368],
                    "1000100057": [1000130368],
                },
            },
        },
        {
            "name": "狗垫",
            "trigger": {
                "api_source": "compliance_page_query",
                "field": "cat_id",
                "condition": "equals",
                "value": 1745,
            },
            "action": {
                "type": "set_properties",
                "task_name": "其他合规信息",
                "properties": {
                    "4094": [69448],
                    "4095": [69450],
                    "4096": [69452],
                    "1000100023": [1000130000],
                    "1000100056": [1000130368],
                    "1000100057": [1000130368],
                },
            },
        },
    ],
}