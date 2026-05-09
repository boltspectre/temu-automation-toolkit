from collections import defaultdict


def extract_real_pic_list_json(data_json=None):
    """
    :param data_json:
    :return: 输出带spu，规则，图片，sku的spu_list
    """
    # 根层字段
    success = data_json.get("success")
    error_code = data_json.get("error_code")

    # 数据在 result.items
    result_obj = data_json.get("result", {})
    if not isinstance(result_obj, dict):
        raise ValueError("Expected 'result' to be an object")

    items = result_obj.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Expected 'result.items' to be a list")

    total = result_obj.get("total", 0)

    extracted_list = []

    for item in items:
        if not isinstance(item, dict):
            continue

        # 提取字段（按你要求）
        spu_id = item.get("spu_id")
        goods_id = item.get("goods_id")
        goods_status = item.get("goods_status")
        upload_status = item.get("upload_status")
        material_img_url = (item.get("material_img_url") or "").strip()
        label_image_list = item.get("label_image_list", [])
        is_same_sku = item.get("is_same_sku")

        # SKU 列表：优先用根级 sku_info，否则 fallback 到 same_sku_vo.sku_list
        sku_info = item.get("sku_info")
        if not sku_info and "same_sku_vo" in item:
            same_sku_vo = item["same_sku_vo"]
            if isinstance(same_sku_vo, dict):
                sku_info = same_sku_vo.get("sku_list", [])
        sku_info = sku_info or []

        # 提取规则检查结果
        rule_check_result_list = []
        rules = item.get("rule_check_result_list", [])
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict):
                    rule_check_result_list.append({
                        "check_type": rule.get("check_type"),
                        "rule_name": rule.get("rule_name"),
                        "rule_status": rule.get("rule_status"),
                        "rule_status_toast": rule.get("rule_status_toast")
                    })

        # 构造最终对象
        extracted = {
            "spu_id": spu_id,
            "goods_id": goods_id,
            "goods_status": goods_status,
            "upload_status": upload_status,
            "material_img_url": material_img_url,
            "label_image_list": label_image_list,
            "is_same_sku": is_same_sku,
            "sku_info": sku_info,
            "rule_check_result_list": rule_check_result_list,
        }


        extracted_list.append(extracted)

    result = {
        "success": success,
        "error_code": error_code,
        "total": total,
        "data": extracted_list
    }

    return result

def build_real_pic_payload(data_json, upload_img_urls):
    """
    构建 Temu 实拍图 payload，强制包含 position=1 和 position=2
    每个 position 必须有至少一张图
    """
    spu_id = data_json["spu_id"]
    goods_id = data_json["goods_id"]
    is_same_sku = data_json.get("is_same_sku", False)
    sku_list = [sku["sku_id"] for sku in data_json.get("sku_info", [])]

    # 强制检查 position 1 和 2
    required_positions = [1, 2]
    real_picture_info_list = []

    for pos in required_positions:
        img_urls = upload_img_urls.get(str(pos), [])
        if not img_urls:
            raise ValueError(f"Position {pos} 必须提供至少一张图片！当前为空。")

        # 构造该 position 的 image_list（支持多张）
        image_list_for_this_pos = [
            {"image_url": url, "position_type": 2}
            for url in img_urls
        ]

        # 所有 SKU 共用这些图
        sku_photo_info_list = [
            {"sku_id": sku_id, "image_list": image_list_for_this_pos}
            for sku_id in sku_list
        ]

        real_picture_info_list.append({
            "position": pos,
            "is_same_sku": 1 if is_same_sku else 0,
            "sku_photo_info_list": sku_photo_info_list
        })

    return {
        "confirm_type": 4,
        "spu_id": spu_id,
        "goods_id": goods_id,
        "real_picture_info_list": real_picture_info_list
    }


# ===== 使用示例 =====
if __name__ == "__main__":
    payload = None

    dict1 = {'1': ['https://pos.file.temu.com/flash-tag/20150c20c0f/da7a98d9-739d-49b0-b510-af125a7f21b9_1071x768.jpeg'], '2': ['https://pos.file.temu.com/flash-tag/20150c20c0f/da7a98d9-739d-49b0-b510-af125a7f21b9_1071x768.jpeg']}

    img_url1 = "https://www.xhxwk.com/2.jpeg"

    dict1['1'].append(img_url1)
    dict1['2'].append(img_url1)

    print(dict1)

    # 打印验证结构
    import json

    upload_img_urls = {
        "1": [
            "https://your-cdn.com/new_label_1_a.jpg",
            "https://your-cdn.com/new_label_1_b.jpg",  # 第二张图（可选）
            "https://your-cdn.com/new_label_1_c.jpg"  # 第三张图
        ],
        "2": [
            "https://your-cdn.com/new_label_2_a.jpg",
            "https://your-cdn.com/new_label_2_b.jpg"
        ]
    }


    spu_data_list = extract_real_pic_list_json()

    for spu_data in spu_data_list['data']:
        # print(spu_data)

        # 再次检测标签 加拿大-小地毯 代号135 异常
        for rule in spu_data['rule_check_result_list']:
            if rule['check_type'] == 135 and rule['rule_status'] == 4:
                # print(spu_data['label_image_list'])

                # 把原来的标签转化成可上传的标签，用于后续上传（增量模式）
                pos_dict = defaultdict(list)
                [pos_dict[str(img['position'])].append(img['image']) for img in spu_data['label_image_list']]
                upload_img_urls = dict(pos_dict)
                # print(upload_img_urls)

                # 插入副标签图 上传图片逻辑一致 插图也一致 可以依次插入 但批图需要skc联合其他页面进行spu查询skc
                upload_img_urls['1'].append(img_url1)
                upload_img_urls['2'].append(img_url1)
                print(upload_img_urls)

                # exit(1)
                if spu_data['spu_id'] == 8350774240:

                    payload = build_real_pic_payload(spu_data, upload_img_urls)
                    import json

                    print(json.dumps(payload, indent=2, ensure_ascii=False))
