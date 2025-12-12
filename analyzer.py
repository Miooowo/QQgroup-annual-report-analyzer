# -*- coding: utf-8 -*-
import re
import random
import string
import math
import jieba
from collections import Counter, defaultdict
import config as cfg
from utils import (
    extract_emojis,
    is_emoji,
    parse_timestamp,
    clean_text,
    calculate_entropy,
    analyze_single_chars,
)

jieba.setLogLevel(jieba.logging.INFO)

class ChatAnalyzer:
    def __init__(self, data):
        self.data = data
        self.messages = data.get('messages', [])
        self.chat_name = data.get('chatName', data.get('chatInfo', {}).get('name', '未知群聊'))
        self.uin_to_name = {}
        self.msgid_to_sender = {}
        self.word_freq = Counter()
        self.word_samples = defaultdict(list)
        self.word_contributors = defaultdict(Counter)
        self.user_msg_count = Counter()
        self.user_char_count = Counter()
        self.user_char_per_msg = {}
        self.user_image_count = Counter()
        self.user_forward_count = Counter()
        self.user_reply_count = Counter()
        self.user_replied_count = Counter()
        self.user_at_count = Counter()
        self.user_ated_count = Counter()
        self.user_emoji_count = Counter()
        self.user_link_count = Counter()
        self.user_night_count = Counter()
        self.user_morning_count = Counter()
        self.user_repeat_count = Counter()
        self.hour_distribution = Counter()
        self.discovered_words = set()
        self.merged_words = {}
        self.single_char_stats = {}  # 单字统计
        self.cleaned_texts = []  # 缓存清洗后的文本
        self._build_mappings()

    def _is_bot_message(self, msg):
        """判断是否为机器人消息（基于 subMsgType）"""
        if not cfg.FILTER_BOT_MESSAGES:
            return False
        
        raw_msg = msg.get('rawMessage', {})
        sub_msg_type = raw_msg.get('subMsgType', 0)
        return sub_msg_type in [577, 65]

    def _build_mappings(self):
        """构建 uin 到 name 的映射，优先保留有效的 name"""
        # 先收集每个 uin 的所有 name（按顺序）和 sendMemberName
        uin_names = defaultdict(list)
        uin_member_names = {}  # 存储最后的 sendMemberName
        
        for msg in self.messages:
            # 跳过机器人消息
            if self._is_bot_message(msg):
                continue
            
            sender = msg.get('sender', {})
            uin = sender.get('uin')
            name = sender.get('name', '').strip()  # 去除首尾空白
            msg_id = msg.get('messageId')
            
            # 收集 name
            if uin and name:
                # 只在 name 与上一个不同时添加
                if not uin_names[uin] or uin_names[uin][-1] != name:
                    uin_names[uin].append(name)
            
            # 收集 sendMemberName（保留最后一个）
            if uin:
                raw_msg = msg.get('rawMessage', {})
                send_member_name = raw_msg.get('sendMemberName', '').strip()
                if send_member_name:
                    uin_member_names[uin] = send_member_name
            
            if msg_id and uin:
                self.msgid_to_sender[msg_id] = uin
        
        # 为每个 uin 选择最合适的 name
        for uin, names in uin_names.items():
            # 从后往前找第一个不等于uin的 name
            chosen_name = None
            for name in reversed(names):
                if name != str(uin):
                    chosen_name = name
                    break
            
            # 如果所有 name 都等于 uin，使用 sendMemberName
            if chosen_name is None:
                if uin in uin_member_names:
                    chosen_name = uin_member_names[uin]
                elif names:
                    chosen_name = names[-1]  # 兜底：使用最后一个
            
            if chosen_name:
                self.uin_to_name[uin] = chosen_name

    def get_name(self, uin):
        return self.uin_to_name.get(uin, f"未知用户({uin})")

    def analyze(self):
        print(f"📊 开始分析: {self.chat_name}")
        print(f"📝 消息数: {len(self.messages)}")
        print("=" * cfg.CONSOLE_WIDTH)
        
        print("\n🧹 预处理文本...")
        self._preprocess_texts()
        
        print("🔤 分析单字独立性...")
        self.single_char_stats = analyze_single_chars(self.cleaned_texts)
        
        print("🔍 新词发现...")
        self._discover_new_words()
        
        print("🔗 词组合并...")
        self._merge_word_pairs()
        
        print("📈 分词统计...")
        self._tokenize_and_count()
        
        print("🎮 趣味统计...")
        self._fun_statistics()
        
        print("🧹 过滤整理...")
        self._filter_results()
        
        print("\n✅ 完成!")

    def _preprocess_texts(self):
        """预处理所有文本"""
        skipped = 0
        bot_filtered = 0
        for msg in self.messages:
            # 跳过机器人消息
            if self._is_bot_message(msg):
                bot_filtered += 1
                continue
            
            content = msg.get('content', {})
            text = content.get('text', '') if isinstance(content, dict) else ''
            cleaned = clean_text(text)
            if cleaned and len(cleaned) >= 1:
                self.cleaned_texts.append(cleaned)
            elif text:
                skipped += 1
        
        if cfg.FILTER_BOT_MESSAGES and bot_filtered > 0:
            print(f"   有效文本: {len(self.cleaned_texts)} 条, 跳过: {skipped} 条, 过滤机器人: {bot_filtered} 条")
        else:
            print(f"   有效文本: {len(self.cleaned_texts)} 条, 跳过: {skipped} 条")

    def _discover_new_words(self):
        """新词发现"""
        ngram_freq = Counter()
        left_neighbors = defaultdict(Counter)
        right_neighbors = defaultdict(Counter)
        total_chars = 0
        
        for text in self.cleaned_texts:
            # 按标点分句
            sentences = re.split(r'[，。！？、；：""''（）\s\n\r,\.!?\(\)]', text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 2:
                    continue
                total_chars += len(sentence)
                
                for n in range(2, min(6, len(sentence) + 1)):
                    for i in range(len(sentence) - n + 1):
                        ngram = sentence[i:i+n]
                        # 跳过纯数字/符号/纯英文
                        if re.match(r'^[\d\s\W]+$', ngram) or re.match(r'^[a-zA-Z]+$', ngram):
                            continue
                        ngram_freq[ngram] += 1
                        if i > 0:
                            left_neighbors[ngram][sentence[i-1]] += 1
                        else:
                            left_neighbors[ngram]['<BOS>'] += 1
                        if i + n < len(sentence):
                            right_neighbors[ngram][sentence[i+n]] += 1
                        else:
                            right_neighbors[ngram]['<EOS>'] += 1
        
        # 筛选新词
        for word, freq in ngram_freq.items():
            if freq < cfg.NEW_WORD_MIN_FREQ:
                continue
            
            # 邻接熵
            left_ent = calculate_entropy(left_neighbors[word])
            right_ent = calculate_entropy(right_neighbors[word])
            min_ent = min(left_ent, right_ent)
            if min_ent < cfg.ENTROPY_THRESHOLD:
                continue
            
            # PMI（内部凝聚度）
            min_pmi = float('inf')
            for i in range(1, len(word)):
                left_freq = ngram_freq.get(word[:i], 0)
                right_freq = ngram_freq.get(word[i:], 0)
                if left_freq > 0 and right_freq > 0:
                    pmi = math.log2((freq * total_chars) / (left_freq * right_freq + 1e-10))
                    min_pmi = min(min_pmi, pmi)
            
            if min_pmi == float('inf'):
                min_pmi = 0
            
            if min_pmi < cfg.PMI_THRESHOLD:
                continue
            
            self.discovered_words.add(word)
        
        # 添加到jieba词典
        for word in self.discovered_words:
            jieba.add_word(word, freq=1000)
        
        print(f"   发现 {len(self.discovered_words)} 个新词")

    def _merge_word_pairs(self):
        """词组合并"""
        bigram_counter = Counter()
        word_right_counter = Counter()
        
        for text in self.cleaned_texts:
            words = [w for w in jieba.cut(text) if w.strip()]
            for i in range(len(words) - 1):
                w1, w2 = words[i].strip(), words[i+1].strip()
                if not w1 or not w2:
                    continue
                if re.match(r'^[\d\W]+$', w1) or re.match(r'^[\d\W]+$', w2):
                    continue
                bigram_counter[(w1, w2)] += 1
                word_right_counter[w1] += 1
        
        # 找出应该合并的词对
        for (w1, w2), count in bigram_counter.items():
            merged = w1 + w2
            if len(merged) > cfg.MERGE_MAX_LEN:
                continue
            if count < cfg.MERGE_MIN_FREQ:
                continue
            
            # 条件概率 P(w2|w1)
            if word_right_counter[w1] > 0:
                prob = count / word_right_counter[w1]
                if prob >= cfg.MERGE_MIN_PROB:
                    self.merged_words[merged] = (w1, w2, count, prob)
                    jieba.add_word(merged, freq=count * 1000)
        
        print(f"   合并 {len(self.merged_words)} 个词组")
        
        # 显示前几个
        if self.merged_words:
            sorted_merges = sorted(self.merged_words.items(), key=lambda x: -x[1][2])[:10]
            for merged, (w1, w2, cnt, prob) in sorted_merges:
                print(f"      {merged}: {w1}+{w2} ({cnt}次, {prob:.0%})")

    def _tokenize_and_count(self):
        """分词统计"""
        for idx, msg in enumerate(self.messages):
            # 跳过机器人消息
            if self._is_bot_message(msg):
                continue
            
            sender_uin = msg.get('sender', {}).get('uin')
            content = msg.get('content', {})
            text = content.get('text', '') if isinstance(content, dict) else ''
            original_text = text
            cleaned = clean_text(text)
            
            if not cleaned:
                continue
            
            words = list(jieba.cut(cleaned))
            emojis = extract_emojis(cleaned)
            words = [w for w in words if not is_emoji(w)]  # 新增：从words中去掉emoji
            all_tokens = words + emojis
            
            for word in all_tokens:
                word = word.strip()
                if not word:
                    continue
                
                # 跳过纯数字/符号
                if re.match(r'^[\d\W]+$', word) and not is_emoji(word):
                    continue
                
                self.word_freq[word] += 1
                if sender_uin:
                    self.word_contributors[word][sender_uin] += 1
                if len(self.word_samples[word]) < cfg.SAMPLE_COUNT * 3:
                    self.word_samples[word].append(cleaned)

    def _fun_statistics(self):
        """趣味统计"""
        prev_clean = None  # 改用清理后文本
        prev_sender = None
        
        for msg in self.messages:
            # 跳过机器人消息
            if self._is_bot_message(msg):
                continue
            
            sender_uin = msg.get('sender', {}).get('uin')
            if not sender_uin:
                continue
            
            content = msg.get('content', {})
            text = content.get('text', '') if isinstance(content, dict) else ''
            timestamp = msg.get('timestamp', '')
            
            self.user_msg_count[sender_uin] += 1
            clean = clean_text(text)
            self.user_char_count[sender_uin] += len(clean)
            
            # 图片检测（排除gif）
            if '[图片:' in text:
                if '.gif' not in text.lower():
                    self.user_image_count[sender_uin] += 1
            
            # 转发检测
            if '[合并转发:' in text:
                self.user_forward_count[sender_uin] += 1
            
            # 回复统计
            reply_info = content.get('reply') if isinstance(content, dict) else None
            if reply_info:
                self.user_reply_count[sender_uin] += 1
                ref_msg_id = reply_info.get('referencedMessageId')
                if ref_msg_id and ref_msg_id in self.msgid_to_sender:
                    target_uin = self.msgid_to_sender[ref_msg_id]
                    self.user_replied_count[target_uin] += 1
            
            # @统计
            raw = msg.get('rawMessage', {})
            elements = raw.get('elements', [])
            for elem in elements:
                if elem.get('elementType') == 1:
                    text_elem = elem.get('textElement', {})
                    at_type = text_elem.get('atType', 0)
                    at_uid = text_elem.get('atUid', '')
                    if at_type > 0 and at_uid and at_uid != '0':
                        self.user_at_count[sender_uin] += 1
                        self.user_ated_count[at_uid] += 1
            
            # 表情统计（包括emoji、[表情:]、gif）
            emojis = extract_emojis(clean)
            gif_count = text.lower().count('.gif')
            bracket_emoji_count = text.count('[表情:')
            emoji_count = len(emojis) + bracket_emoji_count + gif_count
            if emoji_count > 0:
                self.user_emoji_count[sender_uin] += emoji_count
            
            # 链接统计
            if '[链接:' in text or re.search(r'https?://', text):
                self.user_link_count[sender_uin] += 1
            
            # 时段统计
            hour = parse_timestamp(timestamp)
            if hour is not None:
                self.hour_distribution[hour] += 1
                if hour in cfg.NIGHT_OWL_HOURS:
                    self.user_night_count[sender_uin] += 1
                if hour in cfg.EARLY_BIRD_HOURS:
                    self.user_morning_count[sender_uin] += 1
            
            # 复读统计（用清理后文本，且内容要有意义）
            if clean and len(clean) >= 2:
                if clean == prev_clean and sender_uin != prev_sender:
                    self.user_repeat_count[sender_uin] += 1
            
            prev_clean = clean if clean else prev_clean  # 空消息不更新
            prev_sender = sender_uin
        
        # 计算人均字数
        for uin in self.user_msg_count:
            msg_count = self.user_msg_count[uin]
            char_count = self.user_char_count[uin]
            if msg_count >= 10:
                self.user_char_per_msg[uin] = char_count / msg_count

    def _filter_results(self):
        """过滤结果"""
        filtered_freq = Counter()
        
        for word, freq in self.word_freq.items():
            # 长度过滤
            if len(word) < cfg.MIN_WORD_LEN or len(word) > cfg.MAX_WORD_LEN:
                continue
            if freq < cfg.MIN_FREQ:
                continue
            
            # 白名单直接通过
            if word in cfg.WHITELIST:
                filtered_freq[word] = freq
                continue
            
            # 黑名单跳过
            if word in cfg.BLACKLIST:
                continue
            
            # 单字特殊处理（采用旧版逻辑）
            if len(word) == 1:
                if is_emoji(word):
                    pass  # emoji保留
                else:
                    stats = self.single_char_stats.get(word)
                    if stats:
                        total, indep, ratio = stats
                        if ratio < cfg.SINGLE_MIN_SOLO_RATIO or indep < cfg.SINGLE_MIN_SOLO_COUNT:
                            continue
                    else:
                        continue
            
            # 纯数字跳过
            if re.match(r'^[\d\s]+$', word):
                continue
            
            # 纯标点跳过
            if all(c in string.punctuation or c in '，。！？；：、""''（）【】' for c in word):
                continue
            
            filtered_freq[word] = freq
        
        self.word_freq = filtered_freq
        
        # 采样
        for word in self.word_samples:
            samples = self.word_samples[word]
            if len(samples) > cfg.SAMPLE_COUNT:
                self.word_samples[word] = random.sample(samples, cfg.SAMPLE_COUNT)
        
        print(f"   过滤后 {len(self.word_freq)} 个词")

    def get_top_words(self, n=None):
        n = n or cfg.TOP_N
        return self.word_freq.most_common(n)

    def get_word_detail(self, word):
        return {
            'word': word,
            'freq': self.word_freq.get(word, 0),
            'samples': self.word_samples.get(word, []),
            'contributors': [(self.get_name(uin), count) 
                           for uin, count in self.word_contributors[word].most_common(cfg.CONTRIBUTOR_TOP_N)]
        }

    def get_fun_rankings(self):
        rankings = {}
        
        def fmt(counter, top_n=cfg.RANK_TOP_N):
            return [(self.get_name(uin), count) for uin, count in counter.most_common(top_n)]
        
        rankings['话痨榜'] = fmt(self.user_msg_count)
        rankings['字数榜'] = fmt(self.user_char_count)
        
        sorted_avg = sorted(self.user_char_per_msg.items(), key=lambda x: x[1], reverse=True)[:cfg.RANK_TOP_N]
        rankings['长文王'] = [(self.get_name(uin), f"{avg:.1f}字/条") for uin, avg in sorted_avg]
        
        rankings['图片狂魔'] = fmt(self.user_image_count)
        rankings['合并转发王'] = fmt(self.user_forward_count)
        rankings['回复狂'] = fmt(self.user_reply_count)
        rankings['被回复最多'] = fmt(self.user_replied_count)
        rankings['艾特狂'] = fmt(self.user_at_count)
        rankings['被艾特最多'] = fmt(self.user_ated_count)
        rankings['表情帝'] = fmt(self.user_emoji_count)
        rankings['链接分享王'] = fmt(self.user_link_count)
        rankings['深夜党'] = fmt(self.user_night_count)
        rankings['早起鸟'] = fmt(self.user_morning_count)
        rankings['复读机'] = fmt(self.user_repeat_count)
        
        return rankings
    
    def export_json(self):
        """导出JSON格式结果（包含uin信息）"""
        result = {
            'chatName': self.chat_name,
            'messageCount': len(self.messages),
            'topWords': [
                {
                    'word': word,
                    'freq': freq,
                    'contributors': [
                        {
                            'name': self.get_name(uin), 
                            'uin': uin,
                            'count': count
                        }
                        for uin, count in self.word_contributors[word].most_common(cfg.CONTRIBUTOR_TOP_N)
                    ],
                    'samples': self.word_samples.get(word, [])[:cfg.SAMPLE_COUNT]
                }
                for word, freq in self.get_top_words()
            ],
            'rankings': {},
            'hourDistribution': {str(h): self.hour_distribution.get(h, 0) for h in range(24)}
        }
        
        # 趣味榜单（包含uin）
        def fmt_with_uin(counter, top_n=cfg.RANK_TOP_N):
            return [
                {'name': self.get_name(uin), 'uin': uin, 'value': count}
                for uin, count in counter.most_common(top_n)
            ]
        
        result['rankings']['话痨榜'] = fmt_with_uin(self.user_msg_count)
        result['rankings']['字数榜'] = fmt_with_uin(self.user_char_count)
        
        # 长文王特殊处理
        sorted_avg = sorted(self.user_char_per_msg.items(), key=lambda x: x[1], reverse=True)[:cfg.RANK_TOP_N]
        result['rankings']['长文王'] = [
            {'name': self.get_name(uin), 'uin': uin, 'value': f"{avg:.1f}字/条"}
            for uin, avg in sorted_avg
        ]
        
        result['rankings']['图片狂魔'] = fmt_with_uin(self.user_image_count)
        result['rankings']['合并转发王'] = fmt_with_uin(self.user_forward_count)
        result['rankings']['回复狂'] = fmt_with_uin(self.user_reply_count)
        result['rankings']['被回复最多'] = fmt_with_uin(self.user_replied_count)
        result['rankings']['艾特狂'] = fmt_with_uin(self.user_at_count)
        result['rankings']['被艾特最多'] = fmt_with_uin(self.user_ated_count)
        result['rankings']['表情帝'] = fmt_with_uin(self.user_emoji_count)
        result['rankings']['链接分享王'] = fmt_with_uin(self.user_link_count)
        result['rankings']['深夜党'] = fmt_with_uin(self.user_night_count)
        result['rankings']['早起鸟'] = fmt_with_uin(self.user_morning_count)
        result['rankings']['复读机'] = fmt_with_uin(self.user_repeat_count)
        
        return result
