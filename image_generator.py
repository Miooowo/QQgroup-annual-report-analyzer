# -*- coding: utf-8 -*-

import os
import sys
import json
import math
import asyncio
import base64
from jinja2 import Environment, FileSystemLoader, select_autoescape
import config as cfg
from utils import sanitize_filename

# 尝试导入requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None


# 每个词独立的贡献者颜色
WORD_COLORS = [
    '#DC2626', '#EA580C', '#D97706', '#CA8A04', '#65A30D',
    '#16A34A', '#0D9488', '#0891B2', '#2563EB', '#7C3AED'
]

# 榜单配置 (title, key, icon, unit)
RANKING_CONFIG = [
    ('群聊噪音', '话痨榜', '🏆', '条'),
    ('打字民工', '字数榜', '📝', '字'),
    ('小作文狂', '长文王', '📖', ''),
    ('表情狂人', '表情帝', '😂', '个'),
    ('我的图图', '图片狂魔', '🖼️', '张'),
    ('转发机器', '合并转发王', '📦', '次'),
    ('回复劳模', '回复狂', '💬', '次'),
    ('回复黑洞', '被回复最多', '⭐', '次'),
    ('艾特狂魔', '艾特狂', '📢', '次'),
    ('人气靶子', '被艾特最多', '🎯', '次'),
    ('链接仓鼠', '链接分享王', '🔗', '条'),
    ('阴间作息', '深夜党', '🌙', '条'),
    ('早八怨种', '早起鸟', '🌅', '条'),
    ('复读机器', '复读机', '🔄', '次'),
]


def format_number(value):
    """格式化数字"""
    try:
        return f"{int(value):,}"
    except:
        return str(value)


def truncate_text(text, length=50):
    """截断文本"""
    if not text:
        return ""
    text = text.replace('\n', ' ').strip()
    if len(text) > length:
        return text[:length] + '...'
    return text


def get_avatar_url(uin):
    """获取QQ头像URL"""
    return f"https://q1.qlogo.cn/g?b=qq&nk={uin}&s=640"


def download_image_to_base64(url, timeout=10, retry=2):
    """
    下载图片并转换为base64
    
    Args:
        url: 图片URL
        timeout: 超时时间（秒）
        retry: 重试次数
        
    Returns:
        base64编码的图片数据，失败返回None
    """
    if not REQUESTS_AVAILABLE:
        return None
    
    if not url or not url.startswith('http'):
        return None
    
    # 设置User-Agent，避免被拒绝
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://qzone.qq.com/',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
    }
    
    # 禁用SSL警告（如果需要）
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except:
        pass
    
    for attempt in range(retry + 1):
        try:
            response = requests.get(url, timeout=timeout, stream=True, headers=headers, verify=True)
            if response.status_code == 200:
                # 检查内容长度
                content = response.content
                if len(content) < 100:  # 太小的内容可能是错误页面
                    if attempt < retry:
                        continue
                    return None
                
                image_data = base64.b64encode(content).decode('utf-8')
                # 检测图片类型
                content_type = response.headers.get('Content-Type', 'image/png')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    return f"data:image/jpeg;base64,{image_data}"
                elif 'gif' in content_type:
                    return f"data:image/gif;base64,{image_data}"
                elif 'webp' in content_type:
                    return f"data:image/webp;base64,{image_data}"
                else:
                    return f"data:image/png;base64,{image_data}"
            elif response.status_code == 404:
                # 404直接返回，不需要重试
                return None
        except requests.exceptions.Timeout:
            if attempt < retry:
                continue
            return None
        except requests.exceptions.RequestException:
            if attempt < retry:
                continue
            return None
        except Exception:
            if attempt < retry:
                continue
            return None
    
    return None


def clean_ai_response(text):
    # 清理AI响应中的思考过程标记
    if not text:
        return text
    
    import re
    
    # 移除常见的思考标记模式
    patterns = [
        r'\*Thinking[:\.].*?\*.*?(?=\n\n|\Z)', 
        r'\*\*Examining.*?\*\*.*?(?=\n\n|\Z)',  
        r'<thinking>.*?</thinking>',  
        r'【思考】.*?【/思考】',  
        r'\[思考过程\].*?(?=\n\n|\Z)',  
    ]
    
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    
    # 如果整段都是thinking内容，尝试提取最后一行作为结论
    if cleaned.strip() == '' or len(cleaned.strip()) < 5:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        # 尝试找到不是thinking标记的最后几行
        for line in reversed(lines):
            if not any(marker in line.lower() for marker in ['thinking', 'examining', '思考', 'analysis']):
                if len(line) > 5 and len(line) < 100:  # 合理长度
                    return line
    
    return cleaned.strip()


class AIWordSelector:
    """AI智能选词器"""
    
    SYSTEM_PROMPT = """你是一个专业的群聊文化分析师，擅长识别最具代表性的群聊热词。

你的任务是从候选词列表中选出10个最适合作为年度热词的词汇。

## 选词标准（按重要性排序）：
1. **娱乐意义**：词汇要有趣味性、有梗、能引发共鸣或笑点
2. **群聊特色**：体现这个群独特氛围、文化、黑话或内部梗
3. **使用频率**：在保证有意义的前提下，优先选择高频词
4. **网络流行**：网络热词、流行梗、谐音梗等优先
5. **表达价值**：词汇要有实际表达意义，不是纯粹的功能词

## 必须过滤的无意义词汇类型：
- **功能词**：好的、不是、没有、会、现在、但是、然后、所以、因为等
- **语气词**：啊、呀、呢、吧、吗、哦、嗯、哈等（除非在特定语境下特别有趣）
- **代词**：我、你、他、这、那等
- **常见副词**：很、非常、特别、也、还、就、才、都等
- **无实际意义的词**：在、有、是、上、下、中、里等

## 优先选择的词汇类型：
- 网络流行梗、热词、表情包相关词汇
- 群内特有的黑话、缩写、暗号
- 搞笑表情、emoji组合
- 有趣的口头禅、口头表达
- 独特的表达方式、谐音梗
- 有特色的脏话、粗话（如果有群聊文化特色）
- 能代表群内话题、活动的词汇

## 评估方法：
对于每个候选词，请评估：
1. **娱乐价值**（0-10分）：是否有趣、有梗、能引发共鸣
2. **群聊特色**（0-10分）：是否体现群内独特文化
3. **表达意义**（0-10分）：是否有实际表达价值，不是纯粹功能词
4. **使用频率**：作为参考，但不是唯一标准

**重要**：即使一个词使用频率很高，如果它只是"好的"、"不是"这类无意义功能词，也应该被过滤掉。优先选择频率中等但娱乐价值高的词，而不是频率高但无意义的词。

请从提供的候选词中选出最能代表这个群聊文化的10个词。"""

    def __init__(self):
        self.client = None
        self.model = None
        self._init_client()
    
    def _init_client(self):
        """初始化OpenAI客户端"""
        # 支持从环境变量读取API密钥
        api_key = os.getenv('OPENAI_API_KEY', cfg.OPENAI_API_KEY)
        base_url = os.getenv('OPENAI_BASE_URL', cfg.OPENAI_BASE_URL)
        self.model = os.getenv('OPENAI_MODEL', cfg.OPENAI_MODEL)
        
        if not api_key or api_key == "sk-your-api-key-here":
            print("⚠️ 未配置OpenAI API Key，无法使用AI选词")
            return
        
        if not self.model:
            print("⚠️ 未配置OpenAI模型")
            return
        
        try:
            from openai import OpenAI
            import httpx
            
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=httpx.Client(timeout=120.0)
            )
            print(f"✅ AI客户端初始化成功 (模型: {self.model})")
        except Exception as e:
            print(f"⚠️ OpenAI客户端初始化失败: {e}")
    
    def select_words(self, candidate_words, top_n=200):
        """从候选词中智能选出10个年度热词"""
        if not self.client:
            print("❌ AI未启用，请配置OpenAI API Key")
            return None
        
        # 准备候选词列表（取前top_n个）
        candidates = candidate_words[:top_n]
        
        # 获取无意义词列表，用于AI参考
        meaningless_words = list(cfg.FUNCTION_WORDS)[:50]  # 取前50个作为示例
        meaningless_examples = '、'.join(meaningless_words[:20])  # 显示前20个作为示例
        
        # 构建候选词信息，包含更多上下文
        words_info = []
        for idx, word_data in enumerate(candidates, 1):
            word = word_data['word']
            freq = word_data['freq']
            samples = word_data.get('samples', [])
            
            # 提供更多样本上下文（最多3个样本，每个最多40字符）
            sample_texts = []
            for sample in samples[:3]:
                if sample:
                    sample_texts.append(sample[:40])
            
            if sample_texts:
                samples_preview = ' | '.join(sample_texts)
            else:
                samples_preview = '无样本'
            
            # 计算频率排名（用于AI参考）
            rank_info = f"排名#{idx}"
            
            words_info.append(f"{idx}. {word} ({freq}次, {rank_info}) - 使用示例: {samples_preview}")
        
        words_text = '\n'.join(words_info)
        
        user_prompt = f"""请从以下{len(candidates)}个候选词中选出10个最适合作为年度热词的词汇：

{words_text}

## 选词要求：
1. **严格过滤无意义词汇**：必须排除以下类型的词（系统已配置的无意义词示例：{meaningless_examples}等）：
   - 功能词：好的、不是、没有、会、现在、但是、然后、所以、因为、以及、或者
   - 常见语气词：啊、呀、呢、吧、吗、哦、嗯、哈（除非在例句中特别有趣或有特殊含义）
   - 代词：我、你、他、这、那、这个、那个
   - 无意义副词：很、非常、特别、也、还、就、才、都、全、只、仅
   - 无实际意义的词：在、有、是、上、下、中、里、内、外、前、后
   
   **判断标准**：如果一个词只是语法功能词，没有实际表达意义或娱乐价值，就应该被过滤。即使频率很高，也要优先选择频率中等但有趣的词。

2. **优先选择标准**（按重要性）：
   - 有娱乐价值、有梗、有趣的词
   - 体现群聊特色、内部文化的词
   - 网络流行梗、热词
   - 群内黑话、缩写、暗号
   - 有特色的表达方式

3. **使用频率**：
   - 在保证有意义的前提下，优先选择高频词
   - 但如果高频词都是无意义的功能词，宁愿选择频率中等但有趣的词
   - 不要仅仅因为频率高就选择无意义的词

4. **输出格式**：
   - 直接输出10个序号，用逗号分隔
   - 例如: 1,5,8,12,15,23,30,42,56,78
   - 只输出序号，不要有其他文字或解释

5. **选词策略**：
   - 优先从前100个词中选择（因为频率通常更高）
   - 但如果后面的词特别有趣或有特色，也可以选择
   - 确保选出的10个词都有实际意义和娱乐价值

请仔细分析每个词的娱乐意义和群聊特色，严格过滤无意义词汇，选出最能代表这个群聊文化的10个词。"""

        try:
            print("🤖 AI正在分析并选择年度热词...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.7
            )
            
            # 清理响应中的思考过程
            raw_result = response.choices[0].message.content.strip()
            result = clean_ai_response(raw_result)
            
            # 如果清理后为空，使用原始结果
            if not result:
                result = raw_result
            
            print(f"   AI返回: {result}")
            
            # 解析序号
            indices = []
            for part in result.replace('，', ',').split(','):
                try:
                    idx = int(part.strip())
                    if 1 <= idx <= len(candidates):
                        indices.append(idx - 1)  # 转为0索引
                except:
                    continue
            
            if len(indices) < 10:
                print(f"⚠️ AI只选出{len(indices)}个词，自动补充有意义的高频词...")
                # 补充前面的词直到10个，但跳过无意义词
                for i in range(len(candidates)):
                    if i not in indices and len(indices) < 10:
                        candidate_word = candidates[i]['word']
                        # 跳过无意义词
                        if candidate_word not in cfg.FUNCTION_WORDS and candidate_word not in cfg.BLACKLIST:
                            indices.append(i)
            
            indices = indices[:10]
            selected = [candidates[i] for i in indices]
            
            # 二次验证：检查选出的词是否包含无意义词汇
            filtered_selected = []
            replaced_count = 0
            for word_data in selected:
                word = word_data['word']
                # 检查是否在无意义词列表中
                if word in cfg.FUNCTION_WORDS or word in cfg.BLACKLIST:
                    print(f"   ⚠️ AI选出了无意义词 '{word}'，自动替换...")
                    replaced_count += 1
                    # 从候选词中找一个不在已选列表中的有意义词替换
                    for candidate in candidates:
                        if candidate['word'] not in [w['word'] for w in filtered_selected + selected]:
                            if candidate['word'] not in cfg.FUNCTION_WORDS and candidate['word'] not in cfg.BLACKLIST:
                                filtered_selected.append(candidate)
                                break
                else:
                    filtered_selected.append(word_data)
            
            # 如果替换了词，补充到10个
            if replaced_count > 0:
                print(f"   ℹ️ 已替换 {replaced_count} 个无意义词")
                # 从剩余候选词中补充
                for candidate in candidates:
                    if len(filtered_selected) >= 10:
                        break
                    if candidate['word'] not in [w['word'] for w in filtered_selected]:
                        if candidate['word'] not in cfg.FUNCTION_WORDS and candidate['word'] not in cfg.BLACKLIST:
                            filtered_selected.append(candidate)
            
            filtered_selected = filtered_selected[:10]
            
            print("\n✅ AI选词完成:")
            for i, word_data in enumerate(filtered_selected, 1):
                print(f"   {i}. {word_data['word']} ({word_data['freq']}次)")
            
            return filtered_selected
            
        except Exception as e:
            print(f"❌ AI选词失败: {e}")
            return None


class AIUserPersonalityGenerator:
    """AI群友性格和用词锐评生成器"""
    
    SYSTEM_PROMPT = """你是一个幽默风趣的群聊分析师，擅长通过分析群友的用词习惯来锐评其性格特点。

你的任务是为群友生成一句精辟的性格和用词锐评。要求：
1. 简短有力，20-40字为宜
2. 结合该群友的5个代表性词汇，分析其发言风格和性格特点
3. 可以调侃、可以感慨、可以哲理，但要有趣且准确
4. 语气可以是：毒舌吐槽/温情感慨/哲学思考/冷幽默/谐音梗 等
5. 不要太正经，要有网感
6. 要体现出该群友的独特之处，不能是通用评价

风格参考：
- 如果词汇偏技术向 → "代码是他的第二语言，键盘是他的武器"
- 如果词汇偏搞笑向 → "行走的表情包制造机，群聊的快乐源泉"
- 如果词汇偏文艺向 → "用词如诗，每一句都是对生活的温柔注解"
- 如果词汇偏暴躁向 → "情绪管理大师，用词如刀，句句见血"
- 如果词汇偏佛系 → "岁月静好代言人，用词如禅，心如止水"
"""

    def __init__(self):
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化OpenAI客户端（支持OpenAI兼容的API，如DeepSeek）"""
        # 支持从环境变量读取API密钥
        api_key = os.getenv('OPENAI_API_KEY', cfg.OPENAI_API_KEY)
        base_url = os.getenv('OPENAI_BASE_URL', cfg.OPENAI_BASE_URL)
        self.model = os.getenv('OPENAI_MODEL', cfg.OPENAI_MODEL)
        
        if not api_key or api_key == "sk-your-api-key-here":
            print("⚠️ 未配置OpenAI API Key，将跳过AI群友锐评")
            return
        
        if not self.model:
            print("⚠️ 未配置AI模型，将跳过AI群友锐评")
            return
        
        try:
            from openai import OpenAI
            import httpx
            
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url if base_url else None,
                http_client=httpx.Client(timeout=60.0)
            )
        except Exception as e:
            print(f"⚠️ AI客户端初始化失败: {e}")
    
    def generate_personality_comment(self, user_name, representative_words, user_stats=None):
        """为单个群友生成性格和用词锐评"""
        if not self.client:
            return self._fallback_comment(user_name, representative_words)
        
        # 构建词汇信息
        words_text = '、'.join([f"{w['word']}({w['count']}次)" for w in representative_words])
        
        # 构建用户提示
        stats_text = ""
        if user_stats:
            stats_text = f"""
发言统计：
- 总发言数：{user_stats.get('message_count', 0)}条
- 总字数：{user_stats.get('char_count', 0)}字
- 平均每条：{user_stats.get('avg_chars_per_msg', 0):.1f}字
"""
        
        user_prompt = f"""请为这个群友生成一句性格和用词锐评：

群友名称：{user_name}
代表性词汇（5个）：{words_text}
{stats_text}

请结合这5个词汇的特点，分析该群友的发言风格和性格特征，生成一句精辟的锐评。
直接输出锐评内容，不要加引号或其他格式。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.8
            )
            
            raw_content = response.choices[0].message.content.strip()
            cleaned_content = clean_ai_response(raw_content)
            
            if not cleaned_content or len(cleaned_content) < 5:
                return self._fallback_comment(user_name, representative_words)
            
            return cleaned_content
        except Exception as e:
            print(f"   ⚠️ AI生成失败({user_name}): {e}")
            return self._fallback_comment(user_name, representative_words)
    
    def _fallback_comment(self, user_name, representative_words):
        """备用锐评"""
        words_list = [w['word'] for w in representative_words]
        words_str = '、'.join(words_list[:3])
        return f"用词如{words_list[0] if words_list else '谜'}，风格独特，群聊中的{words_list[1] if len(words_list) > 1 else '独特'}存在"
    
    def generate_batch(self, users_data):
        """批量生成群友锐评"""
        if not self.client:
            print("⚠️ AI未启用，使用默认群友锐评")
            return {u['name']: self._fallback_comment(u['name'], u['words']) for u in users_data}
        
        print("🤖 正在生成AI群友性格锐评...")
        comments = {}
        for i, user_info in enumerate(users_data, 1):
            user_name = user_info['name']
            print(f"   [{i}/{len(users_data)}] {user_name}...", end=' ')
            comment = self.generate_personality_comment(
                user_name,
                user_info['words'],
                user_info.get('stats')
            )
            comments[user_name] = comment
            print(f"✓")
        
        return comments


class AICommentGenerator:
    """AI锐评生成器"""
    
    SYSTEM_PROMPT = """你是一个幽默风趣的群聊分析师，擅长用犀利又不失温度的语言点评网络热词。

你的任务是为QQ群年度热词报告生成一句精辟的锐评。要求：
1. 简短有力，15-30字为宜
2. 可以调侃、可以感慨、可以哲理，但要有趣
3. 结合词语本身的含义和使用场景
4. 语气可以是：毒舌吐槽/温情感慨/哲学思考/冷幽默/谐音梗 等
5. 不要太正经，要有网感

风格参考：
- "哈哈哈" → "快乐是假的，但敷衍是真的"
- "牛逼" → "词汇量告急时的唯一出路"
- "好的" → "成年人最敷衍的三个字"
- "?" → "一个符号，十万种质疑"
- "6" → "当代网友最高效的赞美"""

    def __init__(self):
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化OpenAI客户端（支持OpenAI兼容的API，如DeepSeek）"""
        # 支持从环境变量读取API密钥
        api_key = os.getenv('OPENAI_API_KEY', cfg.OPENAI_API_KEY)
        base_url = os.getenv('OPENAI_BASE_URL', cfg.OPENAI_BASE_URL)
        self.model = os.getenv('OPENAI_MODEL', cfg.OPENAI_MODEL)
        
        if not api_key or api_key == "sk-your-api-key-here":
            print("⚠️ 未配置OpenAI API Key，将跳过AI锐评")
            return
        
        if not self.model:
            print("⚠️ 未配置AI模型，将跳过AI锐评")
            return
        
        try:
            from openai import OpenAI
            import httpx
            
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url if base_url else None,  # 如果为空则使用默认
                http_client=httpx.Client(timeout=60.0)  # 增加超时
            )
            
            # 显示配置信息
            api_provider = "DeepSeek" if "deepseek" in (base_url or "").lower() else "OpenAI"
            print(f"✅ AI客户端初始化成功 ({api_provider}, 模型: {self.model})")
            
            # 调试信息
            if os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'):
                print("🌐 系统代理已自动加载")
                
        except Exception as e:
            print(f"⚠️ AI客户端初始化失败: {e}")
    
    def generate_comment(self, word, freq, samples):
        """为单个词生成锐评"""
        if not self.client:
            return self._fallback_comment(word)
        
        # 构建用户提示
        samples_text = '\n'.join(f'- {s[:50]}' for s in samples[:5]) if samples else '无'
        
        user_prompt = f"""请为这个群聊热词生成一句锐评：

词语：{word}
出现次数：{freq}次
使用样本：
{samples_text}

直接输出锐评内容，不要加引号或其他格式。"""

        try:
            # 尝试调用API，如果失败则降级处理
            response = self.client.chat.completions.create(
                model=self.model,  # 使用实例变量
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=150,
                temperature=0.8
            )
            
            # 清理响应中的思考过程
            raw_content = response.choices[0].message.content.strip()
            cleaned_content = clean_ai_response(raw_content)
            
            # 如果清理后为空或太短，使用备用
            if not cleaned_content or len(cleaned_content) < 5:
                return self._fallback_comment(word)
            
            return cleaned_content
        except Exception as e:
            print(f"   ⚠️ AI生成失败({word}): {e}")
            return self._fallback_comment(word)
    
    def _fallback_comment(self, word):
        """备用锐评"""
        fallbacks = [
            "群友的快乐，简单又纯粹",
            "这个词承载了太多故事",
            "高频出现，必有原因",
            "群聊精华，浓缩于此",
            "每一次使用都是一次认同",
        ]
        import random
        return random.choice(fallbacks)
    
    def generate_batch(self, words_data):
        """批量生成锐评"""
        if not self.client:
            print("⚠️ AI未启用，使用默认锐评")
            return {w['word']: self._fallback_comment(w['word']) for w in words_data}
        
        print("🤖 正在生成AI锐评...")
        comments = {}
        for i, word_info in enumerate(words_data, 1):
            word = word_info['word']
            print(f"   [{i}/{len(words_data)}] {word}...", end=' ')
            comment = self.generate_comment(
                word, 
                word_info['freq'], 
                word_info.get('samples', [])
            )
            comments[word] = comment
            print(f"✓")
        
        return comments


class ImageGenerator:
    """图片报告生成器"""
    
    def __init__(self, analyzer=None, json_path=None, output_dir=None):
        self.analyzer = analyzer
        self.json_data = None
        self.selected_words = []
        self.ai_comments = {}
        self.user_personality_comments = {}  # 群友性格锐评
        self.user_representative_words = []  # 群友代表性词汇
        self.output_dir = output_dir or os.path.dirname(os.path.abspath(cfg.INPUT_FILE))
        # 群友分析单独保存到一个文件夹
        self.personality_output_dir = os.path.join(self.output_dir, '群友分析')
        os.makedirs(self.personality_output_dir, exist_ok=True)
        self.template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        
        if json_path and os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
        elif analyzer:
            self.json_data = analyzer.export_json()
        
        self.enabled = cfg.ENABLE_IMAGE_EXPORT
        self.ai_selector = None
    
    def display_words_for_selection(self):
        """展示词汇供用户选择"""
        if not self.json_data:
            print("❌ 无数据可展示")
            return False
        
        top_words = self.json_data.get('topWords', [])
        if not top_words:
            print("❌ 无热词数据")
            return False
        
        print("\n" + "=" * 70)
        print("📝 请从以下热词中选择 10 个作为年度热词")
        print("=" * 70)
        
        page_size = 50
        total_pages = (len(top_words) + page_size - 1) // page_size
        current_page = 0
        
        while True:
            start = current_page * page_size
            end = min(start + page_size, len(top_words))
            
            print(f"\n📄 第 {current_page + 1}/{total_pages} 页 ({start + 1}-{end})")
            print("-" * 70)
            
            for i in range(start, end):
                word_info = top_words[i]
                word = word_info['word']
                freq = word_info['freq']
                samples = word_info.get('samples', [])
                
                sample_preview = samples[0].replace('\n', ' ')[:25] + '...' if samples and len(samples[0]) > 25 else (samples[0].replace('\n', ' ') if samples else '无样本')
                contributors = word_info.get('contributors', [])
                contrib_str = contributors[0]['name'] if contributors else '未知'
                
                print(f"  {i+1:>3}. {word:<8} ({freq:>4}次) 👤{contrib_str:<10} | {sample_preview}")
            
            print("-" * 70)
            print("📌 [n]下一页 [p]上一页 [v 序号]详情 [s]选择 [q]退出")
            
            cmd = input(">>> ").strip().lower()
            
            if cmd == 'n':
                current_page = min(current_page + 1, total_pages - 1)
            elif cmd == 'p':
                current_page = max(current_page - 1, 0)
            elif cmd == 's':
                return self._get_user_selection(top_words)
            elif cmd.startswith('v'):
                try:
                    idx = int(cmd[1:].strip()) - 1
                    if 0 <= idx < len(top_words):
                        self._show_word_detail(top_words[idx], idx + 1)
                except:
                    print("⚠️ 请输入有效序号")
            elif cmd == 'q':
                return False
        
        return False
    
    def _show_word_detail(self, word_info, idx):
        """显示词汇详情"""
        print(f"\n{'='*60}")
        print(f"【{idx}】{word_info['word']} - {word_info['freq']}次")
        print(f"{'='*60}")
        
        contributors = word_info.get('contributors', [])
        if contributors:
            print("\n👤 贡献者:")
            max_count = contributors[0]['count']
            for i, c in enumerate(contributors[:5], 1):
                bar = '█' * int(c['count'] / max_count * 20)
                print(f"   {i}. {c['name']:<12} {bar} {c['count']}次")
        
        samples = word_info.get('samples', [])
        if samples:
            print(f"\n📋 样本:")
            for i, s in enumerate(samples[:5], 1):
                print(f"   {i}. {s.replace(chr(10), ' ')[:60]}")
        
        input("\n按回车继续...")
    
    def _get_user_selection(self, top_words):
        """获取用户选择"""
        print("\n" + "=" * 60)
        print("📝 输入10个序号 (空格/逗号分隔，支持范围如1-5)")
        
        while True:
            selection = input("\n>>> ").strip()
            if not selection:
                continue
            
            indices = []
            for part in selection.replace(',', ' ').replace('，', ' ').split():
                try:
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        indices.extend(range(start - 1, end))
                    else:
                        indices.append(int(part) - 1)
                except:
                    pass
            
            indices = [i for i in indices if 0 <= i < len(top_words)]
            indices = list(dict.fromkeys(indices))  # 去重保序
            
            if len(indices) < 10:
                print(f"⚠️ 需要10个，当前{len(indices)}个: {[i+1 for i in indices]}")
                continue
            
            indices = indices[:10]
            self.selected_words = [top_words[i] for i in indices]
            
            print("\n✅ 已选:")
            for i, w in enumerate(self.selected_words, 1):
                print(f"   {i}. {w['word']} ({w['freq']}次)")
            
            if input("\n确认? [Y/n]: ").strip().lower() in ('', 'y', 'yes'):
                return True
    
    def _prepare_template_data(self):
        """准备模板数据"""
        max_freq = max(w['freq'] for w in self.selected_words)
        min_freq = min(w['freq'] for w in self.selected_words)
        
        def calc_bar_height(freq):
            if max_freq == min_freq:
                return 80
            normalized = (freq - min_freq) / (max_freq - min_freq)
            return 25 + math.sqrt(normalized) * 75
        
        processed_words = []
        for idx, word_info in enumerate(self.selected_words):
            contributors = word_info.get('contributors', [])
            total = word_info['freq']
            
            # 每个词独立分配颜色给其贡献者
            segments = []
            accounted = 0
            word_contributor_colors = {}
            
            for i, c in enumerate(contributors[:5]):
                color = WORD_COLORS[i % len(WORD_COLORS)]
                word_contributor_colors[c['name']] = color
                percent = (c['count'] / total * 100) if total > 0 else 0
                segments.append({
                    'name': c['name'],
                    'uin': c.get('uin', ''),
                    'count': c['count'],
                    'percent': percent,
                    'color': color
                })
                accounted += c['count']
            
            # 其他
            if accounted < total:
                other = total - accounted
                segments.append({
                    'name': '其他',
                    'uin': '',
                    'count': other,
                    'percent': (other / total * 100),
                    'color': '#6B7280'
                })
            
            # 图例（该词的贡献者）
            legend = []
            for c in contributors[:3]:
                legend.append({
                    'name': c['name'], 
                    'color': word_contributor_colors.get(c['name'], '#6B7280')
                })
            while len(legend) < 3:
                legend.append({'name': '', 'color': 'transparent'})            
            # 主要贡献者文本
            contrib_text = '、'.join(c['name'] for c in contributors[:3]) if contributors else '未知'
            
            # AI锐评
            ai_comment = self.ai_comments.get(word_info['word'], '')
            
            processed_words.append({
                'word': word_info['word'],
                'freq': word_info['freq'],
                'bar_height': calc_bar_height(word_info['freq']),
                'segments': segments,
                'legend': legend,
                'samples': word_info.get('samples', []),
                'contributors_text': contrib_text,
                'top_contributor': contributors[0] if contributors else None,
                'ai_comment': ai_comment,
                'color': WORD_COLORS[idx % len(WORD_COLORS)]
            })
        
        # 榜单数据
        rankings_data = self.json_data.get('rankings', {})
        processed_rankings = []
        
        # 统计每个用户获得第一名的次数
        from collections import defaultdict
        first_place_count = defaultdict(int)  # {uin: count}
        first_place_honors = defaultdict(list)  # {uin: [honor_info]}
        
        for title, key, icon, unit in RANKING_CONFIG:
            data = rankings_data.get(key, [])
            if not data:
                continue
            
            first = data[0] if data else None
            others = data[1:5] if len(data) > 1 else []
            
            # 统计第一名
            if first and first.get('uin'):
                uin = first.get('uin')
                first_place_count[uin] += 1
                first_place_honors[uin].append({
                    'title': title,
                    'icon': icon,
                    'unit': unit,
                    'value': first.get('value', 0)
                })
            
            processed_rankings.append({
                'title': title,
                'icon': icon,
                'unit': unit,
                'first': {
                    'name': first.get('name', '未知'),
                    'uin': first.get('uin', ''),
                    'value': first.get('value', 0),
                    'avatar': get_avatar_url(first.get('uin', '')) if first else ''
                } if first else None,
                'others': [
                    {
                        'name': item.get('name', '未知'),
                        'value': item.get('value', 0),
                        'uin': item.get('uin', ''),
                        'avatar': get_avatar_url(item.get('uin', ''))
                    }
                    for item in others
                ]
            })
        
        # 找出群神人（获得第一名最多的用户）
        champion = None
        if first_place_count:
            champion_uin = max(first_place_count.items(), key=lambda x: x[1])[0]
            champion_count = first_place_count[champion_uin]
            champion_honors = first_place_honors[champion_uin]
            
            # 获取群神人的基本信息（从任意一个榜单中获取）
            for ranking in processed_rankings:
                if ranking['first'] and ranking['first'].get('uin') == champion_uin:
                    champion = {
                        'name': ranking['first']['name'],
                        'uin': champion_uin,
                        'avatar': ranking['first']['avatar'],
                        'first_place_count': champion_count,
                        'honors': champion_honors
                    }
                    break
        
        # 24小时分布
        hour_dist = self.json_data.get('hourDistribution', {})
        max_hour = max((int(hour_dist.get(str(h), 0)) for h in range(24)), default=1)
        peak_hour = max(range(24), key=lambda h: int(hour_dist.get(str(h), 0)))
        
        hour_data = []
        for h in range(24):
            count = int(hour_dist.get(str(h), 0))
            height = max((count / max_hour * 100) if max_hour > 0 else 0, 3)
            hour_data.append({'hour': h, 'count': count, 'height': height})
        
        # 处理群友代表性词汇和锐评
        processed_users = []
        for user_info in self.user_representative_words:
            user_name = user_info['name']
            personality_comment = self.user_personality_comments.get(user_name, '')
            
            processed_users.append({
                'name': user_name,
                'uin': user_info.get('uin', ''),
                'avatar': get_avatar_url(user_info.get('uin', '')),
                'words': user_info['words'],
                'stats': user_info.get('stats', {}),
                'personality_comment': personality_comment
            })
        
        return {
            'chat_name': self.json_data.get('chatName', '未知群聊'),
            'message_count': self.json_data.get('messageCount', 0),
            'selected_words': processed_words,
            'rankings': processed_rankings,
            'champion': champion,  # 群神人信息
            'hour_data': hour_data,
            'peak_hour': peak_hour,
            'user_personalities': processed_users  # 群友性格锐评
        }
    
    def _generate_ai_comments(self, enable_ai=False):
        """生成AI锐评（可静默）"""
        ai_gen = AICommentGenerator()
        if enable_ai and ai_gen.client:
            self.ai_comments = ai_gen.generate_batch(self.selected_words)
        else:
            self.ai_comments = {w['word']: ai_gen._fallback_comment(w['word']) 
                              for w in self.selected_words}
    
    def _generate_user_personality_comments(self, enable_ai=False):
        """生成群友性格和用词锐评"""
        # 从analyzer获取群友代表性词汇
        if self.analyzer:
            self.user_representative_words = self.analyzer.get_user_representative_words(
                top_n_users=10, 
                words_per_user=5
            )
        else:
            # 如果没有analyzer，尝试从json_data中获取（需要额外处理）
            self.user_representative_words = []
        
        if not self.user_representative_words:
            return
        
        # 生成AI锐评
        ai_gen = AIUserPersonalityGenerator()
        if enable_ai and ai_gen.client:
            self.user_personality_comments = ai_gen.generate_batch(self.user_representative_words)
        else:
            self.user_personality_comments = {
                u['name']: ai_gen._fallback_comment(u['name'], u['words']) 
                for u in self.user_representative_words
            }
    
    def generate_html(self):
        """生成HTML"""
        if not self.selected_words:
            print("❌ 未选择热词")
            return None
        
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)
        
        template_path = os.path.join(self.template_dir, 'report_template.html')
        if not os.path.exists(template_path):
            print(f"❌ 模板不存在: {template_path}")
            return None
        
        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html'])
        )
        env.filters['format_number'] = format_number
        env.filters['truncate_text'] = truncate_text
        env.filters['avatar_url'] = get_avatar_url
        
        template = env.get_template('report_template.html')
        data = self._prepare_template_data()
        html_content = template.render(**data)
        
        safe_name = sanitize_filename(self.json_data.get('chatName', '未知'))
        html_path = os.path.join(self.output_dir, f"{safe_name}_年度热词报告.html")
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML: {html_path}")
        return html_path
    
    async def _html_to_image_async(self, html_path, output_path):
        """异步转图片 - 高分辨率"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("❌ 需要: pip install playwright && playwright install chromium")
            return None
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            # 使用 device_scale_factor=3 提高分辨率（3倍）
            context = await browser.new_context(
                viewport={'width': 450, 'height': 800},
                device_scale_factor=3,  # 高清截图
                ignore_https_errors=True
            )
            page = await context.new_page()
            
            # 设置请求拦截，确保外部图片可以加载
            async def handle_route(route):
                request = route.request
                # 对于图片请求，确保允许加载
                if request.resource_type == 'image':
                    await route.continue_()
                else:
                    await route.continue_()
            
            await page.route('**/*', handle_route)
            
            # 使用 file:// 协议加载本地HTML
            file_url = f'file://{os.path.abspath(html_path).replace(os.sep, "/")}'
            await page.goto(file_url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待所有图片真正加载完成（包括头像）
            print("   等待图片加载...")
            try:
                # 更完善的图片加载等待逻辑
                await page.evaluate("""
                    async () => {
                        const images = Array.from(document.images);
                        const promises = images.map((img, index) => {
                            return new Promise((resolve) => {
                                // 如果图片已经加载完成
                                if (img.complete && img.naturalHeight !== 0) {
                                    resolve();
                                    return;
                                }
                                
                                // 监听加载成功
                                img.onload = () => resolve();
                                
                                // 监听加载失败（也继续，避免卡住）
                                img.onerror = () => {
                                    console.warn('图片加载失败:', img.src);
                                    resolve();
                                };
                                
                                // 超时保护（5秒）
                                setTimeout(() => {
                                    console.warn('图片加载超时:', img.src);
                                    resolve();
                                }, 5000);
                                
                                // 如果src为空或无效，立即resolve
                                if (!img.src || img.src === 'undefined' || img.src.startsWith('data:')) {
                                    resolve();
                                }
                            });
                        });
                        
                        await Promise.all(promises);
                        
                        // 额外等待确保渲染完成
                        await new Promise(resolve => setTimeout(resolve, 500));
                    }
                """)
            except Exception as e:
                print(f"   图片加载等待出现异常（继续执行）: {e}")
            
            # 等待网络空闲（确保所有资源加载完成）
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
            except:
                # 如果超时，继续执行
                pass
            
            # 额外等待确保渲染完成
            await page.wait_for_timeout(1000)
            
            height = await page.evaluate('document.body.scrollHeight')
            await page.set_viewport_size({'width': 450, 'height': height + 50})
            await page.wait_for_timeout(500)
            
            # 验证图片是否加载（调试用）
            loaded_images = await page.evaluate("""
                () => {
                    const images = Array.from(document.images);
                    return {
                        total: images.length,
                        loaded: images.filter(img => img.complete && img.naturalHeight > 0).length,
                        failed: images.filter(img => img.complete && img.naturalHeight === 0).length
                    };
                }
            """)
            print(f"   图片加载状态: {loaded_images['loaded']}/{loaded_images['total']} 成功, {loaded_images['failed']} 失败")
            
            # 截图，使用高质量设置
            await page.screenshot(
                path=output_path, 
                full_page=True,
                type='png',
                clip=None  # 使用full_page时clip应为None
            )
            await browser.close()
        
        return output_path

    
    def html_to_image(self, html_path):
        """转图片"""
        safe_name = sanitize_filename(self.json_data.get('chatName', '未知'))
        output_path = os.path.join(self.output_dir, f"{safe_name}_年度热词报告.png")
        
        print("🖼️ 转换为图片...")
        try:
            result = asyncio.run(self._html_to_image_async(html_path, output_path))
            if result:
                print(f"✅ 图片: {output_path}")
                return output_path
        except Exception as e:
            print(f"⚠️ 转换失败: {e}")
        
        return None
    
    def generate_user_personality_html(self):
        """生成独立的群友性格锐评HTML页面"""
        if not self.user_representative_words:
            print("❌ 无群友数据")
            return None
        
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)
        
        template_path = os.path.join(self.template_dir, 'user_personality_template.html')
        if not os.path.exists(template_path):
            print(f"❌ 模板不存在: {template_path}")
            return None
        
        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html'])
        )
        env.filters['format_number'] = format_number
        env.filters['truncate_text'] = truncate_text
        env.filters['avatar_url'] = get_avatar_url
        
        template = env.get_template('user_personality_template.html')
        
        # 准备数据，直接使用头像URL（通过HTTP访问时，外部图片可以正常加载）
        processed_users = []
        for user_info in self.user_representative_words:
            user_name = user_info['name']
            personality_comment = self.user_personality_comments.get(user_name, '')
            uin = user_info.get('uin', '')
            
            # 直接使用头像URL（与年度报告一致，通过HTTP访问时外部图片可以正常加载）
            avatar_url = get_avatar_url(uin) if uin else 'https://q1.qlogo.cn/g?b=qq&nk=0&s=640'

            processed_users.append({
                'name': user_name,
                'uin': uin,
                'avatar': avatar_url,  # 修复：使用avatar_url而不是avatar
                'words': user_info['words'],
                'stats': user_info.get('stats', {}),
                'personality_comment': personality_comment
            })
        
        data = {
            'chat_name': self.json_data.get('chatName', '未知群聊'),
            'message_count': self.json_data.get('messageCount', 0),
            'user_personalities': processed_users
        }
        
        html_content = template.render(**data)
        
        safe_name = sanitize_filename(self.json_data.get('chatName', '未知'))
        html_path = os.path.join(self.personality_output_dir, f"{safe_name}_群友性格锐评.html")
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ 群友锐评HTML: {html_path}")
        return html_path
    
    async def _personality_html_to_image_async(self, html_path, output_path):
        """异步转图片 - 群友锐评专用（900px宽度，高清晰度）"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("❌ 需要: pip install playwright && playwright install chromium")
            return None
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            # 使用 device_scale_factor=3 提高分辨率（与年度报告一致），宽度设为900px
            context = await browser.new_context(
                viewport={'width': 900, 'height': 1200},
                device_scale_factor=3,  # 3倍高清截图，与年度报告一致
                # 允许加载外部资源
                ignore_https_errors=True
            )
            page = await context.new_page()
            
            # 设置请求拦截，确保外部图片可以加载（虽然头像已转为base64，但保留以防万一）
            async def handle_route(route):
                request = route.request
                await route.continue_()
            
            await page.route('**/*', handle_route)
            
            # 使用 file:// 协议加载本地HTML
            file_url = f'file://{os.path.abspath(html_path).replace(os.sep, "/")}'
            await page.goto(file_url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待所有图片真正加载完成（包括头像）
            # 由于头像已转换为base64嵌入HTML，加载会更快更可靠
            print("   等待图片加载...")
            try:
                # 更完善的图片加载等待逻辑
                await page.evaluate("""
                    async () => {
                        const images = Array.from(document.images);
                        if (images.length === 0) {
                            return;
                        }
                        
                        const promises = images.map((img) => {
                            return new Promise((resolve) => {
                                // 如果图片已经加载完成（包括base64图片）
                                if (img.complete && img.naturalHeight !== 0) {
                                    resolve();
                                    return;
                                }
                                
                                // base64图片通常立即加载完成
                                if (img.src && img.src.startsWith('data:')) {
                                    // 给base64图片一点时间渲染
                                    setTimeout(() => resolve(), 100);
                                    return;
                                }
                                
                                // 监听加载成功
                                img.onload = () => resolve();
                                
                                // 监听加载失败（也继续，避免卡住）
                                img.onerror = () => {
                                    resolve();  // 失败也继续
                                };
                                
                                // 超时保护（3秒，base64图片应该很快）
                                setTimeout(() => {
                                    resolve();
                                }, 3000);
                            });
                        });
                        
                        await Promise.all(promises);
                        
                        // 额外等待确保渲染完成
                        await new Promise(resolve => setTimeout(resolve, 300));
                    }
                """)
            except Exception as e:
                print(f"   图片加载等待出现异常（继续执行）: {e}")
            
            # 等待网络空闲（确保所有资源加载完成）
            # base64图片不需要网络，所以这个等待会很快
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except:
                # 如果超时，继续执行（base64图片不需要网络）
                pass
            
            # 额外等待确保渲染完成
            await page.wait_for_timeout(500)
            
            # 获取实际内容高度
            height = await page.evaluate('document.body.scrollHeight')
            await page.set_viewport_size({'width': 900, 'height': height + 50})
            
            # 再次等待确保布局稳定
            await page.wait_for_timeout(500)
            
            # 验证图片是否加载（调试用）
            loaded_images = await page.evaluate("""
                () => {
                    const images = Array.from(document.images);
                    return {
                        total: images.length,
                        loaded: images.filter(img => img.complete && img.naturalHeight > 0).length,
                        failed: images.filter(img => img.complete && img.naturalHeight === 0).length
                    };
                }
            """)
            print(f"   图片加载状态: {loaded_images['loaded']}/{loaded_images['total']} 成功, {loaded_images['failed']} 失败")
            
            # 截图，使用高质量设置
            await page.screenshot(
                path=output_path, 
                full_page=True,
                type='png',
                clip=None  # 使用full_page时clip应为None
            )
            await browser.close()
        
        return output_path
    
    def user_personality_html_to_image(self, html_path):
        """将群友性格锐评HTML转换为图片"""
        safe_name = sanitize_filename(self.json_data.get('chatName', '未知'))
        output_path = os.path.join(self.personality_output_dir, f"{safe_name}_群友性格锐评.png")
        
        print("🖼️ 转换为图片...")
        try:
            result = asyncio.run(self._personality_html_to_image_async(html_path, output_path))
            if result:
                print(f"✅ 图片: {output_path}")
                return output_path
        except Exception as e:
            print(f"⚠️ 转换失败: {e}")
        
        return None
    
    def generate(self, auto_select=False, ai_select=False, non_interactive=False, generate_image=False, enable_ai=False):
        """生成报告
        
        参数:
            auto_select: 自动选择前10个（简单模式）
            ai_select: 使用AI智能选词（从前200个中选出最有趣的10个）
            non_interactive: 非交互模式
            generate_image: 是否生成图片
            enable_ai: 是否启用AI锐评
        """
        if not self.json_data:
            print("❌ 无数据")
            return None, None
        
        # AI 智能选词模式
        if ai_select:
            print("\n" + "=" * 60)
            print("🤖 AI智能选词模式")
            print("=" * 60)
            
            top_words = self.json_data.get('topWords', [])
            if not top_words:
                print("❌ 无热词数据")
                return None, None
            
            # 初始化AI选词器
            if not self.ai_selector:
                self.ai_selector = AIWordSelector()
            
            # AI选词
            self.selected_words = self.ai_selector.select_words(top_words, top_n=200)
            
            if not self.selected_words:
                print("⚠️ AI选词失败，改用自动选择前10个")
                self.selected_words = top_words[:10]
        
        # 简单自动选择模式
        elif auto_select or non_interactive:
            self.selected_words = self.json_data.get('topWords', [])[:10]
            print(f"📝 自动选择前10个热词")
        
        # 交互选择模式
        else:
            if not self.display_words_for_selection():
                return None, None
        
        if not self.selected_words:
            return None, None, None, None
        
        # AI锐评
        self._generate_ai_comments(enable_ai)
        
        # 群友性格和用词锐评
        self._generate_user_personality_comments(enable_ai)
        
        print("\n🎨 生成报告...")
        html_path = self.generate_html()
        if not html_path:
            return None, None, None, None
        
        img_path = None
        if generate_image:
            img_path = self.html_to_image(html_path)
        
        # 生成独立的群友性格锐评页面
        personality_html_path = None
        personality_img_path = None
        if self.user_representative_words:
            print("\n🎭 生成群友性格锐评页面...")
            personality_html_path = self.generate_user_personality_html()
            if personality_html_path and generate_image:
                personality_img_path = self.user_personality_html_to_image(personality_html_path)
        
        # 返回主报告和群友锐评的路径
        # 格式: (主报告html, 主报告图片, 群友锐评html, 群友锐评图片)
        return html_path, img_path, personality_html_path, personality_img_path


def interactive_generate(json_path=None, analyzer=None):
    """交互式选词生成"""
    gen = ImageGenerator(analyzer=analyzer, json_path=json_path)
    gen.enabled = True
    result = gen.generate(auto_select=False, enable_ai=True, generate_image=True)
    # 兼容旧代码：如果返回4个值，只返回前2个
    if result and len(result) == 4:
        html_path, img_path, _, _ = result
        return html_path, img_path
    return result


def auto_generate(json_path=None, analyzer=None):
    """自动选择前10个生成"""
    gen = ImageGenerator(analyzer=analyzer, json_path=json_path)
    gen.enabled = True
    result = gen.generate(auto_select=True, enable_ai=True, generate_image=True)
    # 兼容旧代码：如果返回4个值，只返回前2个
    if result and len(result) == 4:
        html_path, img_path, _, _ = result
        return html_path, img_path
    return result


def ai_generate(json_path=None, analyzer=None):
    """AI智能选词生成"""
    gen = ImageGenerator(analyzer=analyzer, json_path=json_path)
    gen.enabled = True
    result = gen.generate(ai_select=True, enable_ai=True, generate_image=True)
    # 兼容旧代码：如果返回4个值，只返回前2个
    if result and len(result) == 4:
        html_path, img_path, _, _ = result
        return html_path, img_path
    return result


if __name__ == '__main__':
    import glob
    
    print("=" * 60)
    print("🖼️  报告生成器 ")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    else:
        json_files = glob.glob('*_分析结果.json')
        if not json_files:
            print("❌ 未找到JSON文件")
            sys.exit(1)
        if len(json_files) == 1:
            json_path = json_files[0]
        else:
            for i, f in enumerate(json_files, 1):
                print(f"  {i}. {f}")
            json_path = json_files[int(input("选择: ")) - 1]
    
    print(f"\n📂 {json_path}")
    
    print("\n选择模式:")
    print("  1. 交互选词 - 手动选择10个热词")
    print("  2. 自动前10 - 直接选择前10个")
    print("  3. AI智能选词 - 让AI从前200个中挑选最有趣的10个 🤖")
    
    mode = input("\n请选择 [1/2/3]: ").strip()
    
    if mode == '3':
        result = ai_generate(json_path=json_path)
    elif mode == '2':
        result = auto_generate(json_path=json_path)
    else:
        result = interactive_generate(json_path=json_path)
    
    print("\n" + "=" * 60)
    if result:
        if len(result) == 4:
            html_path, img_path, personality_html, personality_img = result
            if html_path:
                print(f"📄 主报告HTML: {html_path}")
            if img_path:
                print(f"🖼️ 主报告图片: {img_path}")
            if personality_html:
                print(f"🎭 群友锐评HTML: {personality_html}")
            if personality_img:
                print(f"🖼️ 群友锐评图片: {personality_img}")
        else:
            html_path, img_path = result
            if html_path:
                print(f"📄 {html_path}")
            if img_path:
                print(f"🖼️ {img_path}")
