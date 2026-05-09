def soup_bs4_tag_to_newline_text(tag):
    # 优先按 <p> 标签分割
    paragraphs = tag.find_all('p')
    if paragraphs:
        return '\n'.join([p.get_text() for p in paragraphs])
    # 无 <p> 标签时，直接用标签内文本并保留原始换行
    return tag.get_text(separator='\n')