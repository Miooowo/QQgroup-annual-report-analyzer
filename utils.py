# -*- coding: utf-8 -*-
import re
import json
import math
from datetime import datetime, timezone, timedelta
from collections import Counter

# 无意义符号集合（装饰性符号，在词频统计中应该被过滤）
MEANINGLESS_SYMBOLS = '⌒☆★◆◇■□▲△●○※§▽▼◐◑◒◓◔◕◖◗◘◙◚◛◜◝◞◟◠◡☀☁☂☃☄☎☏☐☑☒☓☔☕☖☗☘☙☚☛☜☝☞☟☠☡☢☣☤☥☦☧☨☩☪☫☬☭☮☯☰☱☲☳☴☵☶☷☸☹☺☻☼☽☾☿♀♁♂♃♄♅♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚅⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟⚠⚡⚢⚣⚤⚥⚦⚧⚨⚩⚪⚫⚬⚭⚮⚯⚰⚱⚲⚳⚴⚵⚶⚷⚸⚹⚺⚻⚼⚽⚾⚿⛀⛁⛂⛃⛄⛅⛆⛇⛈⛉⛊⛋⛌⛍⛎⛏⛐⛑⛒⛓⛔⛕⛖⛗⛘⛙⛚⛛⛜⛝⛞⛟⛠⛡⛢⛣⛤⛥⛦⛧⛨⛩⛪⛫⛬⛭⛮⛯⛰⛱⛲⛳⛴⛵⛶⛷⛸⛹⛺⛻⛼⛽⛾⛿'

def load_json(filepath):
    """
    使用流式解析加载 JSON 文件，减少内存占用
    对于大文件，只保留必要的字段
    """
    try:
        import ijson
        print(f"📖 使用流式解析加载 JSON 文件...")
        
        with open(filepath, 'rb') as f:
            parser = ijson.parse(f)
            result = {
                'messages': [],
                'chatInfo': {}
            }
            
            current_message = None
            in_messages = False
            message_count = 0
            
            for prefix, event, value in parser:
                if prefix == 'chatInfo.name' and event == 'string':
                    result['chatInfo']['name'] = value
                
                # 开始处理 messages 数组
                elif prefix == 'messages' and event == 'start_array':
                    in_messages = True
                elif prefix == 'messages' and event == 'end_array':
                    in_messages = False
                
                # 处理单个消息
                elif in_messages:
                    if prefix == 'messages.item' and event == 'start_map':
                        current_message = {}
                        message_count += 1
                        if message_count % 10000 == 0:
                            print(f"   已处理 {message_count} 条消息...")
                    
                    elif prefix == 'messages.item' and event == 'end_map':
                        if current_message:
                            result['messages'].append(current_message)
                            current_message = None
                    
                    # 保留必要字段
                    elif current_message is not None:
                        # 消息 ID
                        if prefix == 'messages.item.messageId' and event == 'string':
                            current_message['messageId'] = value
                        
                        # 时间戳
                        elif prefix == 'messages.item.timestamp' and event in ('string', 'number'):
                            current_message['timestamp'] = str(value)
                        
                        # 发送者信息
                        elif prefix == 'messages.item.sender.uin' and event == 'string':
                            if 'sender' not in current_message:
                                current_message['sender'] = {}
                            current_message['sender']['uin'] = value
                        elif prefix == 'messages.item.sender.name' and event == 'string':
                            if 'sender' not in current_message:
                                current_message['sender'] = {}
                            current_message['sender']['name'] = value
                        
                        # 内容
                        elif prefix == 'messages.item.content.text' and event == 'string':
                            if 'content' not in current_message:
                                current_message['content'] = {}
                            current_message['content']['text'] = value
                        
                        # 回复信息
                        elif prefix == 'messages.item.content.reply.referencedMessageId' and event == 'string':
                            if 'content' not in current_message:
                                current_message['content'] = {}
                            if 'reply' not in current_message['content']:
                                current_message['content']['reply'] = {}
                            current_message['content']['reply']['referencedMessageId'] = value
                        
                        # rawMessage 中的关键字段
                        elif prefix == 'messages.item.rawMessage.subMsgType' and event == 'number':
                            if 'rawMessage' not in current_message:
                                current_message['rawMessage'] = {}
                            current_message['rawMessage']['subMsgType'] = value
                        elif prefix == 'messages.item.rawMessage.sendMemberName' and event == 'string':
                            if 'rawMessage' not in current_message:
                                current_message['rawMessage'] = {}
                            current_message['rawMessage']['sendMemberName'] = value
                        
                        # elements 数组（用于 @ 统计）
                        elif 'elements' in prefix:
                            if 'rawMessage' not in current_message:
                                current_message['rawMessage'] = {}
                            if 'elements' not in current_message['rawMessage']:
                                current_message['rawMessage']['elements'] = []
                            
                            # 简化：只保存包含 @ 的元素
                            if 'textElement.atType' in prefix and event == 'number' and value > 0:
                                element = {'elementType': 1, 'textElement': {'atType': value}}
                                current_message['rawMessage']['elements'].append(element)
                            elif 'textElement.atUid' in prefix and event == 'string':
                                if current_message['rawMessage']['elements']:
                                    current_message['rawMessage']['elements'][-1]['textElement']['atUid'] = value
        
        # 确保群名有值
        chat_name = result['chatInfo'].get('name', '未知群聊')
        if not chat_name:
            chat_name = '未知群聊'
            result['chatInfo']['name'] = chat_name
            
        print(f"✅ 成功加载 {len(result['messages'])} 条消息, 群聊: {chat_name}")
        return result
        
    except ImportError:
        print("⚠️ ijson 未安装，使用标准加载（大文件可能导致内存不足）")
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 流式解析失败，尝试标准加载: {e}")
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except MemoryError:
            print("❌ 文件过大，无法加载到内存")
            raise MemoryError("JSON 文件过大，请减小文件大小或增加系统内存")

def extract_emojis(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002300-\U000023FF"
        "]",
        flags=re.UNICODE
    )
    return emoji_pattern.findall(text)

def is_emoji(char):
    if len(char) != 1:
        return False
    code = ord(char)
    emoji_ranges = [
        (0x1F600, 0x1F64F), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF),
        (0x1F1E0, 0x1F1FF), (0x2702, 0x27B0), (0x1F900, 0x1F9FF),
        (0x1FA00, 0x1FA6F), (0x1FA70, 0x1FAFF), (0x2600, 0x26FF), (0x2300, 0x23FF),
    ]
    return any(start <= code <= end for start, end in emoji_ranges)

def parse_timestamp(ts):
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        local_dt = dt.astimezone(timezone(timedelta(hours=8)))
        return local_dt.hour
    except:
        return None

def clean_text(text):
    """清理文本，去除表情、@、回复等干扰内容"""
    if not text:
        return ""
    
    # 1. 去除回复标记 [回复 xxx: yyy]
    text = re.sub(r'\[回复\s+[^\]]*\]', '', text)
    
    # 2. 去除@某人（更彻底的过滤）
    # 匹配 @ 符号及其后面的所有内容（用户名可能包含中文、英文、数字、空格、特殊字符等）
    # 处理多种情况：
    # - @用户名（后面可能有空格、换行、标点等）
    # - @用户名 @用户名（多个连续的@，如"@灰与白 @灰与白"）
    # - @用户名 后面跟着实际消息内容（如"@Princess 他每次想法变得快"）
    # - @用户名（包含空格，如"@Klaxosaur  Princess 马上写肉干"）
    # 
    # 关键：群昵称可能包含空格，需要匹配到实际消息内容开始，确保群昵称本身也被过滤
    
    # 策略：使用更精确的匹配，确保@及其后面的群昵称（包括空格）都被完全过滤
    
    # 第一步：处理@及其后面的群昵称，且后面跟着实际消息内容
    # 这是最常见的情况：@群昵称 实际消息内容
    # 匹配：@ + 群昵称（可能包含空格）+ 空格 + 实际消息内容开始
    # 使用前瞻断言，确保后面跟着实际消息内容（中文或英文单词）
    # 例如："@Princess 他每次想法变得快" -> 匹配 "@Princess "，保留"他每次想法变得快"
    # 例如："@Klaxosaur  Princess 马上写肉干" -> 匹配 "@Klaxosaur  Princess "，保留"马上写肉干"
    # 
    # 匹配策略：
    # 1. @符号
    # 2. 群昵称：可以是中文、英文、数字、下划线、连字符，可能包含空格
    #    - 简单情况：@Princess（不包含空格）
    #    - 复杂情况：@Klaxosaur  Princess（包含空格）
    # 3. 至少一个空格
    # 4. 后面跟着实际消息内容（中文或英文单词）
    #
    # 使用非贪婪匹配，确保只匹配到第一个实际消息内容开始的位置
    # 群昵称模式：[\u4e00-\u9fff\w\-_]+(?:\s+[\u4e00-\u9fff\w\-_]+)*
    # 这表示：至少一个非空格字符，后面可能跟着（空格+非空格字符）的组合
    text = re.sub(r'@[\u4e00-\u9fff\w\-_]+(?:\s+[\u4e00-\u9fff\w\-_]+)*\s+(?=[\u4e00-\u9fff\w])', '', text)
    
    # 第二步：处理多个连续的@（如 "@灰与白 @灰与白"）
    # 匹配：@ + 用户名（不包含空格）+ 空格 + @ + 用户名 + ...
    # 注意：这一步处理的是不包含空格的简单用户名
    text = re.sub(r'@[^\s@\n]+(?:\s+@[^\s@\n]+)*\s*', '', text)
    
    # 第三步：处理单个@及其后面的用户名（用户名可能包含空格，但后面没有实际消息内容）
    # 匹配：@ + 用户名（可能包含空格）+ (空格/换行/结束)
    # 例如："@Klaxosaur  Princess"（消息结束）或 "@Princess"（消息结束）
    text = re.sub(r'@[\u4e00-\u9fff\w\s\-_]+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'@[\u4e00-\u9fff\w\s\-_]+\s*\n', '', text)
    
    # 第四步：处理简单的@用户名（不包含空格，后面没有实际消息内容）
    # 匹配：@ + 用户名 + (空格/换行/结束)
    text = re.sub(r'@[^\s@\n]+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'@[^\s@\n]+\s*\n', '', text)
    
    # 第五步：处理@后面直接跟空格或换行的情况（如 "@ 消息内容"）
    text = re.sub(r'@\s+', '', text)
    
    # 最后清理可能残留的@符号（包括单独的@）
    text = re.sub(r'@+', '', text)
    
    # 额外处理：如果文本开头是群昵称（可能是过滤@后残留的），且后面跟着实际消息内容
    # 例如："Princess 他每次想法变得快" -> 应该变成 "他每次想法变得快"
    # 这种情况可能是因为第一步没有正确匹配，导致@被过滤但群昵称残留
    # 匹配：行首的英文单词（可能是群昵称）+ 空格 + 实际消息内容（中文或英文）
    # 注意：只处理行首的情况，避免误删消息中间的词汇
    # 使用前瞻断言，确保后面跟着实际消息内容
    # 但要注意：不能误删正常的消息内容，所以只处理看起来像群昵称的情况
    # 策略：如果开头是单个英文单词（可能是群昵称），且后面跟着中文或实际消息
    # 使用更保守的匹配：行首 + 英文单词 + 空格 + 中文/英文开始的实际消息
    text = re.sub(r'^[A-Za-z_][A-Za-z0-9_]*\s+(?=[\u4e00-\u9fff\w])', '', text, flags=re.MULTILINE)
    
    # 3. 去除图片标记（更彻底的匹配，包括各种格式）
    # 匹配 [图片: ...] 格式，包括可能包含特殊字符的情况
    text = re.sub(r'\[图片[^\]]*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[图片[^\[\]]*', '', text, flags=re.IGNORECASE)  # 处理未闭合的标记
    
    # 4. 循环去除所有方括号内容（如[表情][链接]等）
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r'\[[^\[\]]*\]', '', text)
    
    # 5. 去除链接
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    
    # 6. 去除类似图片ID的字符串（如 YDO3MCB`PR 这种）
    # 匹配：字母数字+反引号+字母数字的模式
    text = re.sub(r'[A-Z0-9]+`[A-Z0-9]+', '', text)
    
    # 6.1. 去除包含特殊字符的ID类字符串（如 7R%D8、包含%、_、-、}、]等的短字符串）
    # 匹配：3-10个字符，包含字母数字和特殊字符（%、_、-、}、]等），且不包含中文
    # 先匹配包含特殊字符的短字符串
    def remove_id_like(match):
        word = match.group()
        # 如果包含特殊字符且没有中文，很可能是ID
        if re.search(r'[%_\-}\]]', word) and not re.search(r'[\u4e00-\u9fff]', word):
            return ''
        return word
    text = re.sub(r'\b[a-zA-Z0-9%_\-}\]]{3,10}\b', remove_id_like, text)
    
    # 7. 去除无意义符号（如⌒、☆、★等装饰性符号）
    for symbol in MEANINGLESS_SYMBOLS:
        text = text.replace(symbol, '')
    
    # 8. 去除多余空白
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def calculate_entropy(neighbor_freq):
    total = sum(neighbor_freq.values())
    if total == 0:
        return 0
    entropy = 0
    for freq in neighbor_freq.values():
        p = freq / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy

def generate_time_bar(hour_counts, width=20):
    max_count = max(hour_counts.values()) if hour_counts else 1
    lines = []
    for hour in range(24):
        count = hour_counts.get(hour, 0)
        bar_len = int(count / max_count * width) if max_count > 0 else 0
        bar = '█' * bar_len + '░' * (width - bar_len)
        percentage = count * 100 / sum(hour_counts.values()) if sum(hour_counts.values()) > 0 else 0
        lines.append(f"  {hour:02d}:00 {bar} {count:>5} ({percentage:>4.1f}%)")
    return lines

def sanitize_filename(filename):
    """
    清理文件名中的非法字符
    Windows文件名不允许的字符: < > : " / \\ | ? *
    保留原始字符用于显示，仅在文件名中替换
    """
    if not filename:
        return "未命名"
    
    # 替换Windows非法字符为下划线
    illegal_chars = '<>:"/\\|?*'
    sanitized = filename
    for char in illegal_chars:
        sanitized = sanitized.replace(char, '_')
    
    # 去除首尾空格和点号（Windows不允许）
    sanitized = sanitized.strip('. ')
    
    # 如果清理后为空，返回默认名称
    if not sanitized:
        return "未命名"
    
    return sanitized


def analyze_sentiment(text):
    """
    简单的情感分析：判断文本的情感倾向
    返回: 'positive', 'negative', 'neutral'
    """
    if not text or len(text.strip()) < 2:
        return 'neutral'
    
    text_lower = text.lower()
    
    # 正向情感关键词
    positive_keywords = [
        '好', '棒', '赞', '厉害', '优秀', '完美', '喜欢', '爱', '开心', '高兴', '快乐', '幸福',
        '不错', '可以', '支持', '同意', '对', '正确', 'nice', 'good', 'great', 'awesome',
        '哈哈', 'hhh', 'hh', '233', '666', '👍', '😊', '😄', '😁', '😆', '😃', '😍', '❤️',
        '牛逼', '666', '太棒了', '太好了', '真不错', '真棒', '厉害', '强', '👍'
    ]
    
    # 负向情感关键词
    negative_keywords = [
        '不好', '差', '烂', '垃圾', '讨厌', '烦', '生气', '愤怒', '难过', '伤心', '失望',
        '不行', '不对', '错误', '坏', '糟糕', '差劲', '无语', '服了', 'bad', 'terrible',
        '😢', '😭', '😤', '😠', '😡', '💔', '😞', '😔', '😩', '😫',
        '傻逼', 'sb', '垃圾', '废物', '滚', '去死', '烦死了', '气死了'
    ]
    
    # 统计关键词出现次数
    positive_count = sum(1 for keyword in positive_keywords if keyword in text_lower)
    negative_count = sum(1 for keyword in negative_keywords if keyword in text_lower)
    
    # 判断情感倾向
    if positive_count > negative_count and positive_count > 0:
        return 'positive'
    elif negative_count > positive_count and negative_count > 0:
        return 'negative'
    else:
        return 'neutral'

def analyze_single_chars(texts):
    """分析单字的独立出现情况 - 来自旧版"""
    total_count = Counter()
    solo_count = Counter()
    boundary_count = Counter()
    punctuation = set('，。！？、；：""''（）,.!?;:\'"()[]【】《》<>…—～·')
    
    for text in texts:
        # 统计每个字的总出现次数
        for char in text:
            if re.match(r'^[\u4e00-\u9fffa-zA-Z]$', char):
                total_count[char] += 1
        
        # 统计单字消息
        clean_chars = [c for c in text if re.match(r'^[\u4e00-\u9fffa-zA-Z]$', c)]
        if len(clean_chars) == 1:
            solo_count[clean_chars[0]] += 1
        
        # 统计在边界位置的出现
        for i, char in enumerate(text):
            if not re.match(r'^[\u4e00-\u9fffa-zA-Z]$', char):
                continue
            left_ok = (i == 0) or (text[i-1] in punctuation) or (text[i-1].isspace())
            right_ok = (i == len(text)-1) or (text[i+1] in punctuation) or (text[i+1].isspace())
            if left_ok and right_ok:
                boundary_count[char] += 1
    
    result = {}
    for char in total_count:
        total = total_count[char]
        solo = solo_count[char]
        boundary = boundary_count[char]
        independent = solo + boundary * 0.5
        ratio = independent / total if total > 0 else 0
        result[char] = (total, independent, ratio)
    
    return result
