from openai import OpenAI

from config.common_config import config_manager
from lite_modules.LittleTools import clean_and_parse_json


def get_prompt_from_config(type: str) -> str:
    """从SettingPage_ai_speech_content读取提示词配置"""
    type_names = {
        "post_list": "帖子列表",
        "detail_list": "帖子详情",
        "score_list": "虎扑评分"
    }
    type_name = type_names.get(type)

    if not type_name:
        return "你是人工智能助手"

    # 从SettingPage_ai_speech_content读取提示词JSON
    speech_config_str = config_manager.get_or_set_config("SettingPage_ai_speech_content",
                                                         '{"帖子列表": "帮我分析以下帖子列表数据，\n结合回复数，亮评数，推荐数综合判断热度，总结该关键词下的标题特点和情感偏向：\n数据内容:#数据内容#", "帖子详情": "帮我分析以下帖子详情回复数据，\n1.结合点赞数和用户所在IP地址综合判断，总结该帖子的用户发布内容的主要情感\n2.如果地区发言特点明显的话总结出地区更可能出现的相关发言及情感\n3.如果用户之间有因为某些内容讨论热烈的特别罗列并分析原因：\n数据内容:#数据内容#", "虎扑评分": "帮我分析以下虎扑评分数据，\n1.结合点赞数和用户所在地区综合判断，总结该评分对象的评分分布和用户评论的主要情感\n2.如果地区发言特点明显的话总结出地区更可能出现的相关发言及情感：\n数据内容:#数据内容#"}')
    try:
        import json
        speech_dict = json.loads(speech_config_str) if speech_config_str else {}
        prompt = speech_dict.get(type_name, "")
    except:
        prompt = ""

    # 如果没有配置，返回默认提示词
    if not prompt:
        return "你是人工智能助手"

    return prompt


class AiModel:
    def __init__(self, _selected_fields: str = "", _data_fields: str = "", type: str = "", custom_prompt: str = ""):
        # 使用数据库配置管理器替代配置加载器
        self.ai_reqeust_url = config_manager.get_or_set_config("SettingPage_ai_reqeust_url",
                                                               "https://ark.cn-beijing.volces.com/api/v3")
        # AI 模型API密钥 接口
        # 6dd67d94-dd3c-4d75-b798-ccaf30006826
        self.openai_api_key = config_manager.get_or_set_config("SettingPage_ai_token",
                                                               "6dd67d94-dd3c-4d75-b798-ccaf30006826")

        # 模型端点ID配置
        self.model_endpoint = config_manager.get_or_set_config("SettingPage_ai_model_name",
                                                               "doubao-1-5-lite-32k-250115")

        # 创建OpenAI客户端
        self.client = OpenAI(
            # 此为默认路径，您可根据业务所在地域进行配置
            base_url=self.ai_reqeust_url,
            # 从环境变量中获取您的 API Key
            api_key=self.openai_api_key,
        )

        # 读取AI配置
        ai_config_str = config_manager.get_or_set_config("SettingPage_ai_body_content", "")

        # 确定使用的提示词
        if custom_prompt:
            # 使用用户临时修改的提示词
            system_content = custom_prompt
        elif ai_config_str:
            # 从AI配置中读取
            try:
                # 解析JSON配置
                ai_config = clean_and_parse_json(ai_config_str)

                # 检查解析结果是否有效
                if ai_config is not None:
                    # 从配置中获取模型名称
                    self.model_name = ai_config.get("model", "doubao-1-5-lite-32k-250115")

                    # 从配置中获取messages
                    config_messages = ai_config.get("messages", [])

                    # 如果配置中有系统消息，则使用配置中的系统消息
                    if config_messages and any(msg.get("role") == "system" for msg in config_messages):
                        system_content = next(
                            (msg.get("content") for msg in config_messages if msg.get("role") == "system"),
                            "你是人工智能助手")
                    else:
                        # 否则从SettingPage_ai_speech_content读取提示词
                        system_content = get_prompt_from_config(type)
                else:
                    raise Exception("JSON解析结果为空")
            except Exception as e:
                print(f"解析AI配置失败，使用默认配置: {e}")
                self.model_name = "doubao-1-5-lite-32k-250115"
                # 从SettingPage_ai_speech_content读取提示词
                system_content = get_prompt_from_config(type)
        else:
            # 没有自定义配置，使用默认配置
            self.model_name = "doubao-1-5-lite-32k-250115"
            # 从SettingPage_ai_speech_content读取提示词
            system_content = get_prompt_from_config(type)

        # 构建消息 - 将数据内容替换到提示词中的#数据内容#占位符
        user_content = system_content.replace("#数据内容#", _data_fields) if _data_fields else system_content
        self.messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

    def analysis_no_stream(self):
        try:
            # print("----- standard request -----")
            completion = self.client.chat.completions.create(
                # 使用模型端点ID
                model=self.model_endpoint,
                messages=self.messages,
            )
            return completion.choices[0].message.content
        except UnicodeEncodeError as e:
            print(f"编码错误: {e}")
            print(f"错误位置: {e.encoding}")
            print(f"错误对象: {e.object}")
            print(f"错误开始位置: {e.start}")
            print(f"错误结束位置: {e.end}")
            return f"Encoding Error: {str(e)}"
        except Exception as e:
            print(f"请求失败: {e}")
            import traceback
            traceback.print_exc()
            return f"Error: {str(e)}"

    def analysis_with_stream(self):
        try:
            print("----- streaming request -----")
            # 使用模型端点ID
            stream = self.client.chat.completions.create(
                model=self.model_endpoint,
                messages=self.messages,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"流式请求失败: {e}")
            import traceback
            traceback.print_exc()
            yield f"Error: {str(e)}"


if __name__ == '__main__':
    selected_fields = "['你好呀']"
    data_fields = """
        你好"""
    remind_content = """
        输出你不好三个字"""

    ai_doubao = AiModel(selected_fields, data_fields, "detail_list")
    doubao_stream_no = ai_doubao.analysis_no_stream()
    print(doubao_stream_no)

    # ai_doubao = AiModel(selected_fields, data_fields, "detail_list")
    # doubao_result = ai_doubao.analysis_no_stream()
    # for chunk in doubao_result:
    #     print(chunk, end="")
    # print(doubao_result)