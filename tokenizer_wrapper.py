# -*- coding: utf-8 -*-
"""
分词器封装：支持jieba、pkuseg和subword算法（SentencePiece）
优化中文分词效果
"""

import re
import os
from typing import List, Optional
import jieba

# 尝试导入sentencepiece
try:
    import sentencepiece as spm
    SENTENCEPIECE_AVAILABLE = True
except ImportError:
    SENTENCEPIECE_AVAILABLE = False
    spm = None

# 尝试导入pkuseg
try:
    import pkuseg
    PKUSEG_AVAILABLE = True
except ImportError:
    PKUSEG_AVAILABLE = False
    pkuseg = None


class TokenizerWrapper:
    """分词器封装类，支持多种分词算法"""
    
    def __init__(self, tokenizer_type='jieba', model_path=None, 
                 use_hmm=True, use_paddle=False, custom_dict_files=None):
        """
        初始化分词器
        
        Args:
            tokenizer_type: 分词器类型，可选 'jieba'、'pkuseg' 或 'subword' (SentencePiece)
            model_path: 模型路径（pkuseg领域模型或SentencePiece模型）
            use_hmm: 是否使用HMM模型（仅jieba）
            use_paddle: 是否使用paddle模式（仅jieba，需要安装paddlepaddle）
            custom_dict_files: 自定义词典文件列表
        """
        self.tokenizer_type = tokenizer_type
        self.model_path = model_path
        self.use_hmm = use_hmm
        self.use_paddle = use_paddle
        self.sp_model = None
        self.pkuseg_model = None
        self.custom_words = set()  # 自定义词汇集合
        
        # 处理subword模式
        if tokenizer_type == 'subword':
            if not SENTENCEPIECE_AVAILABLE:
                print("⚠️ SentencePiece未安装，回退到jieba分词")
                print("💡 安装命令: pip install sentencepiece")
                self.tokenizer_type = 'jieba'
            elif model_path and os.path.exists(model_path):
                try:
                    self.sp_model = spm.SentencePieceProcessor()
                    self.sp_model.load(model_path)
                    print(f"✅ 加载SentencePiece模型: {model_path}")
                except Exception as e:
                    print(f"⚠️ 加载SentencePiece模型失败: {e}，回退到jieba分词")
                    self.tokenizer_type = 'jieba'
            else:
                print("⚠️ 未提供SentencePiece模型，回退到jieba分词")
                self.tokenizer_type = 'jieba'
        
        # 处理pkuseg模式
        elif tokenizer_type == 'pkuseg':
            if not PKUSEG_AVAILABLE:
                print("⚠️ pkuseg未安装，回退到jieba分词")
                print("💡 安装命令: pip install pkuseg")
                self.tokenizer_type = 'jieba'
            else:
                try:
                    # pkuseg支持领域模型：news, web, medicine, tourism等
                    if model_path and model_path in ['news', 'web', 'medicine', 'tourism']:
                        self.pkuseg_model = pkuseg.pkuseg(model_name=model_path)
                        print(f"✅ 加载pkuseg领域模型: {model_path}")
                    else:
                        # 使用默认模型
                        self.pkuseg_model = pkuseg.pkuseg()
                        print("✅ 使用pkuseg默认模型")
                except Exception as e:
                    print(f"⚠️ 加载pkuseg模型失败: {e}，回退到jieba分词")
                    self.tokenizer_type = 'jieba'
        
        # 初始化jieba
        if self.tokenizer_type == 'jieba':
            jieba.setLogLevel(jieba.logging.INFO)
            # 加载自定义词典
            self._load_custom_dicts(custom_dict_files)
            print("✅ 使用jieba分词器")
    
    def _load_custom_dicts(self, custom_dict_files):
        """加载自定义词典文件"""
        if not custom_dict_files:
            return
        
        loaded_count = 0
        for dict_file in custom_dict_files:
            # 支持相对路径和绝对路径
            if not os.path.isabs(dict_file):
                # 相对路径：先尝试当前目录，再尝试项目根目录
                possible_paths = [
                    dict_file,
                    os.path.join(os.path.dirname(__file__), dict_file),
                    os.path.join(os.path.dirname(os.path.dirname(__file__)), dict_file)
                ]
            else:
                possible_paths = [dict_file]
            
            loaded = False
            for path in possible_paths:
                if os.path.exists(path):
                    try:
                        jieba.load_userdict(path)
                        print(f"✅ 加载自定义词典: {path}")
                        loaded_count += 1
                        loaded = True
                        break
                    except Exception as e:
                        print(f"⚠️ 加载词典文件失败 {path}: {e}")
                        break
            
            if not loaded:
                print(f"⚠️ 未找到词典文件: {dict_file}")
        
        if loaded_count > 0:
            print(f"📚 共加载 {loaded_count} 个自定义词典文件")
    
    def add_word(self, word: str, freq: int = 1000):
        """
        添加自定义词汇
        
        Args:
            word: 词汇
            freq: 词频
        """
        if self.tokenizer_type == 'jieba':
            jieba.add_word(word, freq=freq)
        elif self.tokenizer_type == 'pkuseg':
            # pkuseg不支持动态添加词汇，记录用于后处理
            self.custom_words.add(word)
        else:
            # subword模式下，记录自定义词汇用于后处理
            self.custom_words.add(word)
    
    def cut(self, text: str, cut_all: bool = False) -> List[str]:
        """
        对文本进行分词
        
        Args:
            text: 输入文本
            cut_all: 是否全模式分词（仅jieba）
            
        Returns:
            分词结果列表
        """
        if not text or not text.strip():
            return []
        
        if self.tokenizer_type == 'jieba':
            # jieba优化配置
            if cut_all:
                # 全模式：返回所有可能的分词结果
                words = list(jieba.cut(text, cut_all=True, HMM=False))
            else:
                # 精确模式：使用HMM识别未登录词
                words = list(jieba.cut(text, cut_all=False, HMM=self.use_hmm))
            
            # 过滤空白字符
            words = [w.strip() for w in words if w.strip()]
            return words
            
        elif self.tokenizer_type == 'pkuseg':
            # pkuseg分词
            words = self.pkuseg_model.cut(text)
            # 过滤空白字符
            words = [w.strip() for w in words if w.strip()]
            return words
            
        else:
            # 使用SentencePiece进行subword分词
            return self._subword_tokenize(text)
    
    def _subword_tokenize(self, text: str) -> List[str]:
        """
        使用SentencePiece进行subword分词
        
        Args:
            text: 输入文本
            
        Returns:
            分词结果列表
        """
        if not self.sp_model:
            # 如果没有模型，回退到字符级分词
            return list(text)
        
        try:
            # SentencePiece分词
            pieces = self.sp_model.encode(text, out_type=str)
            
            # 后处理：合并自定义词汇
            if self.custom_words:
                pieces = self._merge_custom_words(pieces, text)
            
            # 过滤空白字符
            pieces = [p.strip() for p in pieces if p.strip()]
            return pieces
        except Exception as e:
            print(f"⚠️ SentencePiece分词失败: {e}，使用字符级分词")
            return [c for c in text if c.strip()]
    
    def _merge_custom_words(self, pieces: List[str], original_text: str) -> List[str]:
        """
        合并自定义词汇（将subword片段合并为完整词）
        
        Args:
            pieces: subword片段列表
            original_text: 原始文本
            
        Returns:
            合并后的词汇列表
        """
        if not self.custom_words:
            return pieces
        
        result = []
        i = 0
        text_lower = original_text.lower()
        
        while i < len(pieces):
            matched = False
            # 检查是否能匹配自定义词汇
            for custom_word in sorted(self.custom_words, key=len, reverse=True):
                custom_lower = custom_word.lower()
                # 检查从当前位置开始的片段是否能组成自定义词
                remaining_pieces = ''.join(pieces[i:])
                if remaining_pieces.startswith(custom_lower) or custom_lower in remaining_pieces:
                    # 尝试匹配
                    matched_pieces = []
                    matched_text = ''
                    j = i
                    while j < len(pieces) and len(matched_text) < len(custom_word):
                        matched_pieces.append(pieces[j])
                        matched_text = ''.join(matched_pieces)
                        if matched_text == custom_word or matched_text == custom_lower:
                            result.append(custom_word)
                            i = j + 1
                            matched = True
                            break
                        j += 1
                    if matched:
                        break
            
            if not matched:
                result.append(pieces[i])
                i += 1
        
        return result
    
    def train_model(self, texts: List[str], output_model_path: str, 
                   vocab_size: int = 8000, model_type: str = 'bpe'):
        """
        训练SentencePiece模型
        
        Args:
            texts: 训练文本列表
            output_model_path: 输出模型路径
            vocab_size: 词汇表大小
            model_type: 模型类型，'bpe' 或 'unigram'
        """
        if not SENTENCEPIECE_AVAILABLE:
            print("❌ SentencePiece未安装，无法训练模型")
            return False
        
        try:
            # 准备训练数据
            temp_file = output_model_path + '.train.txt'
            with open(temp_file, 'w', encoding='utf-8') as f:
                for text in texts:
                    f.write(text + '\n')
            
            # 训练参数
            spm.SentencePieceTrainer.train(
                input=temp_file,
                model_prefix=output_model_path.replace('.model', ''),
                vocab_size=vocab_size,
                model_type=model_type,
                character_coverage=0.9995,  # 字符覆盖率
                max_sentence_length=4192,
                shuffle_input_sentence=True,
                input_sentence_size=1000000,  # 限制训练数据量
                seed_sentencepiece_size=1000000,
                shrinking_factor=0.75,
                num_threads=4,
                num_sub_iterations=2
            )
            
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            print(f"✅ SentencePiece模型训练完成: {output_model_path}.model")
            return True
            
        except Exception as e:
            print(f"❌ 训练SentencePiece模型失败: {e}")
            return False


def create_subword_tokenizer_from_data(texts: List[str], vocab_size: int = 8000, 
                                      model_dir: str = 'models') -> Optional[TokenizerWrapper]:
    """
    从数据训练并创建subword分词器
    
    Args:
        texts: 训练文本列表
        vocab_size: 词汇表大小
        model_dir: 模型保存目录
        
    Returns:
        TokenizerWrapper实例，如果失败则返回None
    """
    if not SENTENCEPIECE_AVAILABLE:
        print("⚠️ SentencePiece未安装，无法创建subword分词器")
        return None
    
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, 'spm_model.model')
    
    # 如果模型已存在，直接加载
    if os.path.exists(model_path):
        return TokenizerWrapper(tokenizer_type='subword', model_path=model_path)
    
    # 训练新模型
    wrapper = TokenizerWrapper(tokenizer_type='subword')
    if wrapper.train_model(texts, model_path, vocab_size=vocab_size):
        wrapper.sp_model = spm.SentencePieceProcessor()
        wrapper.sp_model.load(model_path)
        wrapper.model_path = model_path
        return wrapper
    
    return None
