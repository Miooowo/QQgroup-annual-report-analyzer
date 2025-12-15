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
    analyze_sentiment,
    MEANINGLESS_SYMBOLS,
)
from tokenizer_wrapper import TokenizerWrapper

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
        # 新增：用户情感统计
        self.user_positive_count = Counter()  # 正向情感发言数
        self.user_negative_count = Counter()  # 负向情感发言数
        self.user_neutral_count = Counter()  # 中立情感发言数
        # 新增：用户@他人统计
        self.user_at_targets = defaultdict(Counter)  # {uin: {target_uin: count}}
        # 新增：用户发言样本（用于AI举例）
        self.user_message_samples = defaultdict(list)  # {uin: [message_texts]}
        # 同词异格映射（别名到标准词的映射）
        self.word_alias_map = getattr(cfg, 'WORD_ALIAS_MAP', {})
        # 初始化分词器
        tokenizer_type = getattr(cfg, 'TOKENIZER_TYPE', 'jieba')
        model_path = getattr(cfg, 'SP_MODEL_PATH', None) or getattr(cfg, 'PKUSEG_MODEL', None)
        use_hmm = getattr(cfg, 'JIEBA_USE_HMM', True)
        use_paddle = getattr(cfg, 'JIEBA_USE_PADDLE', False)
        custom_dict_files = getattr(cfg, 'CUSTOM_DICT_FILES', [])
        self.tokenizer = TokenizerWrapper(
            tokenizer_type=tokenizer_type, 
            model_path=model_path,
            use_hmm=use_hmm,
            use_paddle=use_paddle,
            custom_dict_files=custom_dict_files
        )
        self._build_mappings()
        # 根据群聊名称添加特定词汇
        self._add_chat_name_words()

    def _is_bot_message(self, msg):
        """判断是否为机器人消息（基于 subMsgType）"""
        if not cfg.FILTER_BOT_MESSAGES:
            return False
        
        raw_msg = msg.get('rawMessage', {})
        sub_msg_type = raw_msg.get('subMsgType', 0)
        return sub_msg_type in [577, 65]
    
    def _should_filter_user(self, msg):
        """判断是否应该过滤该用户的消息"""
        sender = msg.get('sender', {})
        name = sender.get('name', '').strip()
        uin = sender.get('uin', '')
        
        # 检查用户名是否在过滤列表中
        if name:
            for filtered_name in cfg.FILTERED_USERS:
                if filtered_name in name:
                    return True
        
        # 检查 sendMemberName
        raw_msg = msg.get('rawMessage', {})
        send_member_name = raw_msg.get('sendMemberName', '').strip()
        if send_member_name:
            for filtered_name in cfg.FILTERED_USERS:
                if filtered_name in send_member_name:
                    return True
        
        # 检查 uin_to_name 映射中的名称
        if uin and uin in self.uin_to_name:
            mapped_name = self.uin_to_name[uin]
            for filtered_name in cfg.FILTERED_USERS:
                if filtered_name in mapped_name:
                    return True
        
        return False

    def _build_mappings(self):
        """构建 uin 到 name 的映射，优先保留有效的 name"""
        # 先收集每个 uin 的所有 name（按顺序）和 sendMemberName
        uin_names = defaultdict(list)
        uin_member_names = {}  # 存储最后的 sendMemberName
        
        for msg in self.messages:
            # 跳过机器人消息
            if self._is_bot_message(msg):
                continue
            
            # 跳过被过滤的用户（在构建映射时也要过滤，避免将过滤用户加入映射）
            # 注意：这里需要先检查 sender.name，因为 uin_to_name 映射还未构建完成
            sender = msg.get('sender', {})
            name = sender.get('name', '').strip()
            raw_msg = msg.get('rawMessage', {})
            send_member_name = raw_msg.get('sendMemberName', '').strip()
            
            # 简单检查用户名是否包含过滤关键词
            should_filter = False
            if name:
                for filtered_name in cfg.FILTERED_USERS:
                    if filtered_name in name:
                        should_filter = True
                        break
            if not should_filter and send_member_name:
                for filtered_name in cfg.FILTERED_USERS:
                    if filtered_name in send_member_name:
                        should_filter = True
                        break
            
            if should_filter:
                continue
            
            uin = sender.get('uin')
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
    
    def _add_chat_name_words(self):
        """根据群聊名称添加特定词汇到词典"""
        chat_name_words = getattr(cfg, 'CHAT_NAME_WORDS', {})
        if not chat_name_words:
            return
        
        # 检查群聊名称是否匹配
        added_words = []
        for chat_keyword, words_to_add in chat_name_words.items():
            if chat_keyword in self.chat_name:
                for word in words_to_add:
                    # 添加到分词器词典
                    self.tokenizer.add_word(word, freq=2000)  # 设置较高词频，确保被识别
                    added_words.append(word)
                    print(f"   📝 根据群名「{self.chat_name}」添加词汇: {word}")
        
        if added_words:
            print(f"   ✅ 共添加 {len(added_words)} 个群名相关词汇: {', '.join(added_words)}")

    def _normalize_word(self, word):
        """同词异格处理：将别名映射到标准词"""
        if word in self.word_alias_map:
            return self.word_alias_map[word]
        return word
    
    def _is_id_like_string(self, word):
        """判断是否为ID类字符串（图片ID、消息ID等）"""
        if not word:
            return False
        
        # 长度检查：ID通常在3-20个字符之间（包括短ID如7R%D8、0ED3V）
        if len(word) < 3 or len(word) > 20:
            return False
        
        # 如果包含特殊字符（如%、_、-、}、]等），很可能是ID
        if re.search(r'[%_\-}\]]', word):
            return True
        
        # 必须是字母数字组合（不包含中文、标点等）
        if not re.match(r'^[a-zA-Z0-9]+$', word):
            return False
        
        # 必须包含至少一个字母和一个数字
        has_letter = bool(re.search(r'[a-zA-Z]', word))
        has_digit = bool(re.search(r'[0-9]', word))
        
        if not (has_letter and has_digit):
            return False
        
        # 对于短字符串（3-5个字符），如果字母数字混合，很可能是ID
        if len(word) <= 5:
            # 如果全是数字或全是字母，不是ID
            if re.match(r'^[0-9]+$', word) or re.match(r'^[a-zA-Z]+$', word):
                return False
            # 字母数字混合的短字符串，很可能是ID
            return True
        
        # 对于长字符串（6-20个字符），字母数量应该占多数（至少50%）
        letter_count = len(re.findall(r'[a-zA-Z]', word))
        if letter_count < len(word) * 0.5:
            return False
        
        # 排除常见的英文单词（长度在6-20之间的常见词）
        # 这里可以添加更多常见词，但为了性能，只检查一些明显的
        common_words = {'password', 'username', 'account', 'message', 'picture', 'image'}
        if word.lower() in common_words:
            return False
        
        return True

    def analyze(self):
        print(f"📊 开始分析: {self.chat_name}")
        print(f"📝 消息数: {len(self.messages)}")
        print("=" * cfg.CONSOLE_WIDTH)
        
        print("\n🧹 预处理文本...")
        self._preprocess_texts()
        
        # 如果使用subword分词器且没有模型，尝试从数据训练
        if (self.tokenizer.tokenizer_type == 'subword' and 
            not self.tokenizer.sp_model and 
            len(self.cleaned_texts) > 100):
            print("🔧 训练SentencePiece模型...")
            from tokenizer_wrapper import create_subword_tokenizer_from_data
            vocab_size = getattr(cfg, 'SP_VOCAB_SIZE', 8000)
            # 使用部分数据训练（避免太慢）
            train_texts = self.cleaned_texts[:min(10000, len(self.cleaned_texts))]
            new_tokenizer = create_subword_tokenizer_from_data(
                train_texts, 
                vocab_size=vocab_size
            )
            if new_tokenizer:
                self.tokenizer = new_tokenizer
        
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
            
            # 跳过被过滤的用户
            if self._should_filter_user(msg):
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
        
        # 添加到分词器词典
        for word in self.discovered_words:
            self.tokenizer.add_word(word, freq=1000)
        
        print(f"   发现 {len(self.discovered_words)} 个新词")

    def _merge_word_pairs(self):
        """词组合并"""
        bigram_counter = Counter()
        word_right_counter = Counter()
        
        for text in self.cleaned_texts:
            words = [w for w in self.tokenizer.cut(text) if w.strip()]
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
                    self.tokenizer.add_word(merged, freq=count * 1000)
        
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
            
            # 跳过被过滤的用户
            if self._should_filter_user(msg):
                continue
            
            sender_uin = msg.get('sender', {}).get('uin')
            content = msg.get('content', {})
            text = content.get('text', '') if isinstance(content, dict) else ''
            original_text = text
            cleaned = clean_text(text)
            
            if not cleaned:
                continue
            
            words = list(self.tokenizer.cut(cleaned))
            emojis = extract_emojis(cleaned)
            words = [w for w in words if not is_emoji(w)]  # 新增：从words中去掉emoji
            all_tokens = words + emojis
            
            for word in all_tokens:
                word = word.strip()
                if not word:
                    continue
                
                # 过滤@符号及其相关内容（额外检查，确保没有遗漏）
                if word.startswith('@') or '@' in word:
                    continue
                
                # 额外检查：如果词汇看起来像是群昵称（单独出现的英文单词，且可能是过滤@后残留的）
                # 这种情况应该已经在clean_text中处理，但为了保险起见，这里也检查
                # 注意：这个检查比较保守，只过滤明显是群昵称的情况
                # 如果词汇是纯英文单词且长度较短（可能是群昵称），且不在常用词列表中，可能需要过滤
                # 但这样可能误删，所以暂时不处理，让clean_text函数处理
                
                # 跳过纯数字/符号
                if re.match(r'^[\d\W]+$', word) and not is_emoji(word):
                    continue
                
                # 过滤包含特殊字符的字符串（如7R%D8、包含%、_、-、}、]等）
                # 这些通常是图片ID、消息ID等无意义标识符
                if re.search(r'[%_\-}\]]', word) and not re.search(r'[\u4e00-\u9fff]', word):
                    # 如果包含特殊字符且没有中文，很可能是ID
                    continue
                
                # 过滤无意义符号词汇（如⌒、☆、★等）
                # 如果词只包含无意义符号，跳过
                if all(c in MEANINGLESS_SYMBOLS for c in word):
                    continue
                # 如果词包含无意义符号且没有其他有意义字符，跳过
                if word and all(c in MEANINGLESS_SYMBOLS or c in string.punctuation or c in '，。！？；：、""''（）【】' or c.isspace() for c in word):
                    continue
                
                # 过滤ID类字符串（图片ID、消息ID等）
                # 匹配：3-20个字符，主要是字母数字组合，包括短ID如7R%D8、0ED3V
                if self._is_id_like_string(word):
                    continue
                
                # 提前过滤黑名单（性能优化：避免统计后再过滤）
                if word in cfg.BLACKLIST:
                    continue
                
                # 过滤虚词（不计入统计）
                if word in cfg.FUNCTION_WORDS:
                    continue
                
                # 同词异格处理：将别名映射到标准词
                normalized_word = self._normalize_word(word)
                
                # 统计标准词（如果映射了，统计标准词；否则统计原词）
                self.word_freq[normalized_word] += 1
                if sender_uin:
                    self.word_contributors[normalized_word][sender_uin] += 1
                if len(self.word_samples[normalized_word]) < cfg.SAMPLE_COUNT * 3:
                    # 只收集有意义的样本（过滤掉只包含图片标记、ID等的无意义内容）
                    if self._is_meaningful_sample(cleaned):
                        self.word_samples[normalized_word].append(cleaned)

    def _fun_statistics(self):
        """趣味统计"""
        prev_clean = None  # 改用清理后文本
        prev_sender = None
        
        for msg in self.messages:
            # 跳过机器人消息
            if self._is_bot_message(msg):
                continue
            
            # 跳过被过滤的用户
            if self._should_filter_user(msg):
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
                        # 记录@的目标用户
                        self.user_at_targets[sender_uin][at_uid] += 1
            
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
            
            # 情感分析统计
            if clean and len(clean) >= 2:
                sentiment = analyze_sentiment(clean)
                if sentiment == 'positive':
                    self.user_positive_count[sender_uin] += 1
                elif sentiment == 'negative':
                    self.user_negative_count[sender_uin] += 1
                else:
                    self.user_neutral_count[sender_uin] += 1
                
                # 收集发言样本（最多保存10条有意义的样本）
                if self._is_meaningful_sample(clean) and len(self.user_message_samples[sender_uin]) < 10:
                    # 只保存长度适中的样本（10-100字符）
                    if 10 <= len(clean) <= 100:
                        self.user_message_samples[sender_uin].append(clean)
            
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
            
            # 虚词过滤（不计入统计）
            if word in cfg.FUNCTION_WORDS:
                continue
            
            # 过滤包含特殊字符的字符串（如7R%D8、包含%、_、-、}、]等）
            # 这些通常是图片ID、消息ID等无意义标识符
            if re.search(r'[%_\-}\]]', word) and not re.search(r'[\u4e00-\u9fff]', word):
                # 如果包含特殊字符且没有中文，很可能是ID
                continue
            
            # 过滤ID类字符串（图片ID、消息ID等）
            if self._is_id_like_string(word):
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
            
            # 过滤无意义符号词汇（如⌒、☆、★等）
            # 如果词只包含无意义符号，跳过
            if all(c in MEANINGLESS_SYMBOLS for c in word):
                continue
            # 如果词包含无意义符号且没有其他有意义字符，跳过
            if word and all(c in MEANINGLESS_SYMBOLS or c in string.punctuation or c in '，。！？；：、""''（）【】' or c.isspace() for c in word):
                continue
            
            filtered_freq[word] = freq
        
        self.word_freq = filtered_freq
        
        # 采样并过滤无意义样本
        for word in list(self.word_samples.keys()):
            samples = self.word_samples[word]
            # 过滤无意义样本
            meaningful_samples = [s for s in samples if self._is_meaningful_sample(s)]
            if len(meaningful_samples) > cfg.SAMPLE_COUNT:
                self.word_samples[word] = random.sample(meaningful_samples, cfg.SAMPLE_COUNT)
            else:
                self.word_samples[word] = meaningful_samples
        
        print(f"   过滤后 {len(self.word_freq)} 个词")

    def get_top_words(self, n=None):
        n = n or cfg.TOP_N
        return self.word_freq.most_common(n)

    def _is_filtered_user_by_uin(self, uin):
        """根据uin判断用户是否应该被过滤"""
        if not uin:
            return False
        # 检查映射中的名称
        if uin in self.uin_to_name:
            name = self.uin_to_name[uin]
            for filtered_name in cfg.FILTERED_USERS:
                if filtered_name in name:
                    return True
        return False
    
    def _is_meaningful_sample(self, text):
        """判断样本是否有意义（过滤掉只包含图片标记、ID等的无意义内容）"""
        if not text or len(text.strip()) < 2:
            return False
        
        # 去除空白后检查
        text_clean = text.strip()
        
        # 再次清理图片标记（确保彻底清理）
        text_clean = re.sub(r'\[图片[^\]]*\]', '', text_clean, flags=re.IGNORECASE)
        text_clean = re.sub(r'\[图片[^\[\]]*', '', text_clean, flags=re.IGNORECASE)
        text_clean = re.sub(r'[A-Z0-9]+`[A-Z0-9]+', '', text_clean)  # 去除图片ID格式
        text_clean = text_clean.strip()
        
        # 如果清理后为空，认为无意义
        if not text_clean:
            return False
        
        # 如果只包含图片标记、ID等，认为无意义
        # 检查是否只包含类似图片ID的字符串（字母数字+特殊字符）
        if re.match(r'^[A-Z0-9`\-_\s]+$', text_clean):
            return False
        
        # 检查是否包含图片标记残留
        if '[图片' in text_clean.lower() or '图片:' in text_clean.lower():
            return False
        
        # 检查是否只包含方括号内容
        text_no_brackets = re.sub(r'\[[^\]]*\]', '', text_clean)
        if not text_no_brackets.strip():
            return False
        
        # 检查是否包含至少一个中文字符或常见标点
        if not re.search(r'[\u4e00-\u9fff，。！？、；：""''（）]', text_clean):
            # 如果没有中文，至少要有一些有意义的英文单词（长度>=2）
            words = re.findall(r'[a-zA-Z]{2,}', text_clean)
            if len(words) == 0:
                return False
        
        return True
    
    def get_word_detail(self, word):
        # 过滤掉被过滤用户的贡献者
        filtered_contributors = [
            (self.get_name(uin), count)
            for uin, count in self.word_contributors[word].most_common(cfg.CONTRIBUTOR_TOP_N * 2)
            if not self._is_filtered_user_by_uin(uin)
        ][:cfg.CONTRIBUTOR_TOP_N]  # 取前N个
        
        return {
            'word': word,
            'freq': self.word_freq.get(word, 0),
            'samples': [s for s in self.word_samples.get(word, []) 
                       if self._is_meaningful_sample(s)],
            'contributors': filtered_contributors
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
                        for uin, count in self.word_contributors[word].most_common(cfg.CONTRIBUTOR_TOP_N * 2)
                        if not self._is_filtered_user_by_uin(uin)
                    ][:cfg.CONTRIBUTOR_TOP_N],  # 过滤后取前N个
                    'samples': [s for s in self.word_samples.get(word, [])[:cfg.SAMPLE_COUNT * 2]
                               if self._is_meaningful_sample(s)][:cfg.SAMPLE_COUNT]
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
    
    def get_user_representative_words(self, top_n_users=10, words_per_user=5):
        """
        获取每个用户的代表性词汇
        
        Args:
            top_n_users: 选择前N个活跃用户
            words_per_user: 每个用户选择N个代表性词汇
            
        Returns:
            List[Dict]: 每个用户的信息，包含name, uin, words(代表性词汇列表), stats(统计数据)
        """
        # 从word_contributors反向统计每个用户使用的词汇
        user_word_freq = defaultdict(Counter)  # {uin: {word: count}}
        
        for word, contributors in self.word_contributors.items():
            # 跳过无意义词
            if word in cfg.FUNCTION_WORDS or word in cfg.BLACKLIST:
                continue
            # 跳过单字（除非是emoji）
            if len(word) == 1 and not is_emoji(word):
                continue
            
            # 过滤字母数字组合（如5C、VXA等）
            if re.match(r'^[a-zA-Z0-9]+$', word) and len(word) <= 5:
                # 如果只包含字母和数字，且长度较短，很可能是无意义的ID或代码
                # 但保留较长的有意义组合（如"iPhone"等）
                if not any(c.isalpha() and c.islower() for c in word):
                    # 如果全是大写字母和数字，很可能是无意义的
                    continue
            
            # 过滤特殊符号（如⌒、☆等）
            if re.match(r'^[^\u4e00-\u9fff\w\s]+$', word):
                # 只包含特殊符号，没有中文、英文、数字
                continue
            
            # 过滤纯符号组合（使用统一的MEANINGLESS_SYMBOLS）
            if all(c in MEANINGLESS_SYMBOLS for c in word):
                continue
            
            for uin, count in contributors.items():
                # 跳过被过滤的用户
                if self._is_filtered_user_by_uin(uin):
                    continue
                user_word_freq[uin][word] += count
        
        # 选择最活跃的top_n_users个用户（按消息数）
        top_users = [uin for uin, _ in self.user_msg_count.most_common(top_n_users * 2)]
        # 过滤掉被过滤的用户
        top_users = [uin for uin in top_users if not self._is_filtered_user_by_uin(uin)][:top_n_users]
        
        result = []
        for uin in top_users:
            user_words = user_word_freq.get(uin, Counter())
            if not user_words:
                continue
            
            # 选择每个用户最有代表性的words_per_user个词
            # 优先选择：1. 频率高 2. 不是无意义词 3. 有实际意义
            selected_words = []
            for word, count in user_words.most_common(words_per_user * 5):
                # 再次过滤无意义词
                if word in cfg.FUNCTION_WORDS or word in cfg.BLACKLIST:
                    continue
                # 跳过单字（除非是emoji）
                if len(word) == 1 and not is_emoji(word):
                    continue
                # 跳过纯数字/符号
                if re.match(r'^[\d\W]+$', word) and not is_emoji(word):
                    continue
                
                # 过滤字母数字组合（如5C、VXA等）
                if re.match(r'^[a-zA-Z0-9]+$', word) and len(word) <= 5:
                    # 如果只包含字母和数字，且长度较短，很可能是无意义的ID或代码
                    # 但保留较长的有意义组合（如"iPhone"等）
                    if not any(c.isalpha() and c.islower() for c in word):
                        # 如果全是大写字母和数字，很可能是无意义的
                        continue
                
                # 过滤特殊符号（如⌒、☆等）
                if re.match(r'^[^\u4e00-\u9fff\w\s]+$', word):
                    # 只包含特殊符号，没有中文、英文、数字
                    continue
                
                # 过滤纯符号组合（使用统一的MEANINGLESS_SYMBOLS）
                if all(c in MEANINGLESS_SYMBOLS for c in word):
                    continue
                
                selected_words.append({
                    'word': word,
                    'count': count
                })
                if len(selected_words) >= words_per_user:
                    break
            
            if not selected_words:
                continue
            
            # 获取用户统计数据
            message_count = self.user_msg_count.get(uin, 0)
            char_count = self.user_char_count.get(uin, 0)
            emoji_count = self.user_emoji_count.get(uin, 0)
            
            # 计算平均每小时发言数（假设分析的时间跨度，这里用总消息数估算）
            # 如果无法准确计算，使用总消息数作为参考
            total_messages = len(self.messages)
            if total_messages > 0:
                # 估算：假设群聊活跃期为30天，每天24小时
                estimated_hours = 30 * 24
                messages_per_hour = message_count / estimated_hours if estimated_hours > 0 else 0
            else:
                messages_per_hour = 0
            
            # 情感统计
            positive_count = self.user_positive_count.get(uin, 0)
            negative_count = self.user_negative_count.get(uin, 0)
            neutral_count = self.user_neutral_count.get(uin, 0)
            total_sentiment = positive_count + negative_count + neutral_count
            if total_sentiment > 0:
                positive_ratio = positive_count / total_sentiment
                negative_ratio = negative_count / total_sentiment
                neutral_ratio = neutral_count / total_sentiment
            else:
                positive_ratio = negative_ratio = neutral_ratio = 0
            
            # 最常@的群友（前3名）
            at_targets = self.user_at_targets.get(uin, Counter())
            top_at_targets = []
            for target_uin, count in at_targets.most_common(3):
                target_name = self.get_name(target_uin)
                top_at_targets.append({'name': target_name, 'count': count})
            
            # 最常用的表情（从样本中提取）
            user_samples = self.user_message_samples.get(uin, [])
            emoji_list = []
            for sample in user_samples[:20]:  # 只分析前20个样本
                emojis = extract_emojis(sample)
                emoji_list.extend(emojis)
            top_emojis = [emoji for emoji, _ in Counter(emoji_list).most_common(3)]
            
            user_stats = {
                'message_count': message_count,
                'char_count': char_count,
                'avg_chars_per_msg': self.user_char_per_msg.get(uin, 0),
                'messages_per_hour': round(messages_per_hour, 2),
                'emoji_count': emoji_count,
                'emoji_usage_rate': round(emoji_count / message_count, 2) if message_count > 0 else 0,
                'top_emojis': top_emojis,
                'sentiment': {
                    'positive_count': positive_count,
                    'negative_count': negative_count,
                    'neutral_count': neutral_count,
                    'positive_ratio': round(positive_ratio, 2),
                    'negative_ratio': round(negative_ratio, 2),
                    'neutral_ratio': round(neutral_ratio, 2),
                },
                'top_at_targets': top_at_targets,
                'message_samples': user_samples[:5]  # 最多5个样本用于AI举例
            }
            
            result.append({
                'name': self.get_name(uin),
                'uin': uin,
                'words': selected_words,
                'stats': user_stats
            })
        
        return result
    
    def _is_filtered_user_by_uin(self, uin):
        """根据uin判断用户是否被过滤"""
        if not uin:
            return True
        
        name = self.uin_to_name.get(uin, '')
        if not name:
            return False
        
        for filtered_name in cfg.FILTERED_USERS:
            if filtered_name in name:
                return True
        
        return False
