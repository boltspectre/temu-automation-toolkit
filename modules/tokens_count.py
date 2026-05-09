import tiktoken

def ai_tokens_count(type: str = None, text: str = None, file_name: str = None):
    enc = tiktoken.get_encoding("cl100k_base")
    if type == "text":
        text = text
    elif type == "file":
        text = open(f"{file_name}", encoding="utf-8").read()
    tokens = enc.encode(text)
    length = len(tokens)
    return f"{length}",


if __name__ == '__main__':
    text = "{adasdas,dasda}"
    aa = ai_tokens_count(type="text", text=text)
    print(aa[0])