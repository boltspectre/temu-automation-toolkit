import base64

import cv2
import ddddocr
import numpy as np
import requests
from loguru import logger


class Captcha:
    def __init__(self):
        self.session = requests.session()
        # 滑块验证码
        self.slide = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
        # 图片识别验证码
        self.indentify = ddddocr.DdddOcr(det=False, ocr=True, show_ad=False)
        # 目标检测模型 点选
        self.det = ddddocr.DdddOcr(det=True, ocr=True, show_ad=False)

    def sent_request(self, method, url, headers=None, **kwargs):
        """
        发送请求
        :param method: 请求方法
        :param url: 请求地址
        :param kwargs: 请求参数
        :return: 响应对象
        """
        if not headers:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36",
                "Accept": "*/*",
            }

        if method == "GET":
            return self.session.get(url, headers=headers, **kwargs)
        elif method == "POST":
            return self.session.post(url, headers=headers, **kwargs)

    def slide_match(self, shade_image_url, cutout_image_url, _type_shade=None, _type_cutout=None):
        """
        滑动验证码匹配：计算小图（滑块）在大图（背景）中的横向偏移量

        参数：
            shade_image_url (str/bytes)：大图（背景图）数据，支持URL字符串、Base64字符串或原始字节
            cutout_image_url (str/bytes)：小图（滑块图）数据，支持URL字符串、Base64字符串或原始字节
            _type_shade (str, optional)：大图类型，可选"url"或"base64"，默认自动判断
            _type_cutout (str, optional)：小图类型，可选"url"或"base64"，默认自动判断

        返回：
            int：小图在大图中的X轴偏移量（匹配失败可能返回0或负数，取决于底层实现）

        异常：
            - requests.exceptions.RequestException：URL请求失败时抛出
            - base64.binascii.Error：Base64解码失败时抛出
            - ValueError：Base64字符串格式错误（无逗号分隔）时抛出
        """
        # 尝试最多3次匹配（当前逻辑首次执行即返回，预留重试扩展）
        for i in range(1, 4):
            # 解析大图数据
            if "http" in shade_image_url or _type_shade == "url":
                # 若为URL，发送GET请求获取图片字节
                big_bytes = self.sent_request("GET", url=shade_image_url).content
            elif "base64" in shade_image_url or _type_shade == "base64":
                # 若为Base64，分割头部并解码
                header, encoded = shade_image_url.split(",", 1)  # 假设格式为"header,encoded"
                big_bytes = base64.b64decode(encoded)
            else:
                # 否则直接使用原始字节数据
                big_bytes = shade_image_url

            # 解析小图数据（逻辑同大图）
            if "http" in cutout_image_url or _type_cutout == "url":
                small_bytes = self.sent_request("GET", url=cutout_image_url).content
            elif "base64" in cutout_image_url or _type_cutout == "base64":
                header, encoded = cutout_image_url.split(",", 1)
                small_bytes = base64.b64decode(encoded)
            else:
                small_bytes = cutout_image_url

            # 调用ddddocr的滑动匹配接口，simple_target=True启用简单模式
            result_x = self.slide.slide_match(small_bytes, big_bytes, simple_target=True)
            logger.trace(f"匹配到的X轴偏移量: {result_x}")
            return result_x

    def identify_img(self, img_data, _type=None):
        """
        识别图片中的验证码内容（基于ddddocr的分类接口）

        参数：
            img_data (str/bytes)：输入的图片数据，支持三种格式：
                - URL字符串（如"https://example.com/captcha.png"）
                - Base64编码字符串（如"data:image/png;base64,xxxx..."）
                - 原始字节数据（bytes类型）
            _type (str, optional)：图片数据类型，可选值为"url"、"base64"、"bytes"。
                若为None，将自动根据img_data内容判断类型（优先检测base64和url特征）

        返回：
            str：识别出的验证码文本结果（具体格式取决于ddddocr模型输出）

        异常：
            - requests.exceptions.RequestException：当_type为"url"且请求失败时抛出
            - base64.binascii.Error：当_type为"base64"且解码失败时抛出
            - ValueError：当_type为"base64"但字符串格式错误（无逗号分隔）时抛出
        """
        # 自动判断图片类型（当未指定_type时）
        if not _type:
            if "base64" in img_data:
                _type = "base64"  # 包含"base64"特征字符串，判定为Base64格式
            elif "http" in img_data:
                _type = "url"  # 包含"http"特征字符串，判定为URL格式
            else:
                _type = "bytes"  # 否则默认为原始字节数据

        # 根据类型解析图片数据为字节流
        if _type == "url":
            # 从URL下载图片，获取字节数据
            yzm_bytes = self.sent_request("GET", url=img_data).content
        elif _type == "base64":
            # 分割Base64前缀（如"data:image/png;base64,"）与编码内容
            header, encoded = img_data.split(",", 1)
            # 解码Base64字符串为字节数据
            yzm_bytes = base64.b64decode(encoded)
        else:
            # 直接使用原始字节数据
            yzm_bytes = img_data

        # 调用ddddocr的分类接口进行验证码识别
        result = self.indentify.classification(yzm_bytes)
        return result

    def click(self, img=None, content=None):
        if content:
            img_content = content
        elif 'http' in img:
            img_content = requests.get(img).content
        else:
            base_code = img.split(',', 1)[1]
            img_content = base64.b64decode(base_code)
        with open('../test.jpg', 'wb') as f:
            f.write(img_content)
        # 执行目标检测
        poses = self.det.detection(img_content)
        print("检测到的坐标位置:", poses)

        # 将字节数据转换为OpenCV图像格式
        nparr = np.frombuffer(img_content, np.uint8)
        im = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 遍历所有检测到的位置并绘制矩形框
        for box in poses:
            x1, y1, x2, y2 = box
            # 绘制红色矩形框
            im = cv2.rectangle(im, (x1, y1), (x2, y2), color=(0, 0, 255), thickness=2)

            # 可选：在框上方添加标签
            label = f"({x1},{y1})-({x2},{y2})"
            cv2.putText(im, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # 可选：显示结果
        # cv2.imshow("Detection Result", im)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()