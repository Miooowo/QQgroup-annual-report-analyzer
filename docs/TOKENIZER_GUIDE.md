# 分词器使用指南

本项目支持三种分词算法：jieba（默认）、pkuseg（高准确率）和 SentencePiece subword 分词。

## 分词器类型对比

| 特性 | jieba | pkuseg | SentencePiece |
|------|-------|--------|---------------|
| 准确率 | 88.42% (F1) | 96.88% (F1) | 中等 |
| 速度 | 快 (0.82s) | 慢 (9.49s) | 中等 |
| 内存占用 | 低 | 中等 | 中等 |
| OOV处理 | 一般 | 好 | 很好 |
| 网络新词 | 一般 | 好 | 好 |
| 自定义词典 | ✅ | ❌ | ❌ |
| 领域模型 | ❌ | ✅ | ❌ |
| 推荐场景 | 实时性要求高 | 准确率要求高 | 混合语言 |

## 分词器详细说明

### 1. jieba 分词（默认）

- **优点**：
  - 成熟稳定，对中文支持好
  - 速度快，资源占用少
  - 支持动态添加自定义词汇
  - 支持自定义词典文件
  - 无需训练模型

- **缺点**：
  - 对未登录词（OOV）处理能力有限
  - 对网络新词、特殊表达可能不够准确

- **配置选项**：
  - `JIEBA_USE_HMM`: 是否使用HMM模型（推荐开启，提高准确率）
  - `JIEBA_USE_PADDLE`: 是否使用paddle模式（需要安装paddlepaddle，准确率更高但速度较慢）

### 2. pkuseg 分词（高准确率）

- **优点**：
  - **准确率高**（F1分数96.88，优于jieba的88.42）
  - 支持多领域模型（新闻、网络、医学、旅游等）
  - 对未登录词处理能力强
  - 适合对准确率要求高的场景

- **缺点**：
  - 速度较慢（比jieba慢约10倍）
  - 不支持动态添加自定义词汇
  - 不支持自定义词典文件

- **领域模型**：
  - `news`: 新闻领域
  - `web`: 网络文本（推荐用于QQ群聊）
  - `medicine`: 医学领域
  - `tourism`: 旅游领域

### 3. SentencePiece Subword 分词

- **优点**：
  - 能处理未登录词（通过 subword 分解）
  - 对网络新词、特殊表达更灵活
  - 可以学习语料库中的词汇模式
  - 适合处理混合语言（中英文混合）

- **缺点**：
  - 需要训练模型（首次使用较慢）
  - 资源占用稍高
  - 分词结果可能包含 subword 片段

## 配置方法

在 `config.py` 中添加以下配置：

```python
# ============================================
# 分词器配置
# ============================================

# 分词器类型
TOKENIZER_TYPE = 'jieba'  # 可选: 'jieba', 'pkuseg', 'subword'

# jieba配置
JIEBA_USE_HMM = True  # 使用HMM模型（推荐）
JIEBA_USE_PADDLE = False  # 使用paddle模式（可选，需要安装paddlepaddle）

# pkuseg配置
PKUSEG_MODEL = 'web'  # 可选: 'news', 'web', 'medicine', 'tourism'

# SentencePiece配置
SP_MODEL_PATH = None  # 模型路径
SP_VOCAB_SIZE = 8000  # 词汇表大小
SP_MODEL_TYPE = 'bpe'  # 模型类型: 'bpe' 或 'unigram'

# 自定义词典（仅jieba）
CUSTOM_DICT_FILES = ['custom_dict.txt', 'user_names.txt']
```

## 使用场景推荐

### 场景1：实时性要求高（默认）
```python
TOKENIZER_TYPE = 'jieba'
JIEBA_USE_HMM = True
CUSTOM_DICT_FILES = ['custom_dict.txt']
```

### 场景2：准确率要求高（推荐）
```python
TOKENIZER_TYPE = 'pkuseg'
PKUSEG_MODEL = 'web'  # 网络文本领域
```

### 场景3：混合语言、网络新词多
```python
TOKENIZER_TYPE = 'subword'
SP_MODEL_PATH = None  # 自动训练
```

## 自定义词典（仅jieba）

### 词典文件格式

创建 `custom_dict.txt` 文件：

```
# 格式：词语 [词频] [词性]
# 每行一个词

# 网络流行词
yyds 1000
绝绝子 1000
破防 1000

# 群友昵称（词频设置高一些）
张三 3000
李四 3000

# 专业术语
Python 2000
JavaScript 2000
```

### 配置词典文件

```python
CUSTOM_DICT_FILES = ['custom_dict.txt', 'user_names.txt']
```

## 安装依赖

### 基础依赖（jieba）
```bash
pip install jieba>=0.42.1
```

### pkuseg（可选）
```python
pip install pkuseg>=0.0.25
```

### SentencePiece（可选）
```bash
pip install sentencepiece>=0.1.99
```

### PaddlePaddle（可选，用于jieba paddle模式）
```bash
pip install paddlepaddle
```

或安装所有依赖：
```bash
pip install -r requirements.txt
```

## 性能对比

基于MSRA数据集的测试结果：

| 分词器 | F1分数 | 速度 | 推荐场景 |
|--------|--------|------|----------|
| jieba | 88.42% | 0.82s | 实时性要求高 |
| pkuseg | 96.88% | 9.49s | 准确率要求高 |
| SentencePiece | 中等 | 中等 | 混合语言 |

## 选择建议

1. **默认使用 jieba**：适合大多数场景，稳定快速
2. **使用 pkuseg**：当对准确率要求高时（如生成报告、数据分析）
3. **使用 subword**：当遇到大量未登录词、网络新词、特殊表达时

## 注意事项

1. pkuseg首次使用会下载模型，需要网络连接
2. SentencePiece首次使用需要训练模型，可能需要几分钟
3. 训练好的模型会缓存，后续使用会直接加载
4. 如果某个分词器未安装，系统会自动回退到jieba分词
5. 自定义词典仅对jieba有效

## 示例

### 使用jieba（默认，快速）
```python
TOKENIZER_TYPE = 'jieba'
JIEBA_USE_HMM = True
CUSTOM_DICT_FILES = ['custom_dict.txt']
```

### 使用pkuseg（高准确率）
```python
TOKENIZER_TYPE = 'pkuseg'
PKUSEG_MODEL = 'web'  # 网络文本领域，适合QQ群聊
```

### 使用subword（自动训练）
```python
TOKENIZER_TYPE = 'subword'
SP_MODEL_PATH = None  # 自动训练
SP_VOCAB_SIZE = 8000
```
