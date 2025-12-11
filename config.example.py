# -*- coding: utf-8 -*-
INPUT_FILE = "chat.json"
TOP_N = 200
MIN_FREQ = 1
MIN_WORD_LEN = 1
MAX_WORD_LEN = 10

# 新词发现参数
PMI_THRESHOLD = 2.0           
ENTROPY_THRESHOLD = 0.5
NEW_WORD_MIN_FREQ = 20        

# 词组合并参数
MERGE_MIN_FREQ = 30           
MERGE_MIN_PROB = 0.3
MERGE_MAX_LEN = 6

# 单字过滤参数
SINGLE_MIN_SOLO_RATIO = 0.01
SINGLE_MIN_SOLO_COUNT = 5

WHITELIST = set()
BLACKLIST = set()
RANK_TOP_N = 10
CONTRIBUTOR_TOP_N = 10
SAMPLE_COUNT = 10
NIGHT_OWL_HOURS = range(0, 6)
EARLY_BIRD_HOURS = range(6, 9)
OUTPUT_ENCODING = "utf-8"
CONSOLE_WIDTH = 60
ENABLE_IMAGE_EXPORT = True

# ============ 机器人过滤 ============
FILTER_BOT_MESSAGES = True  # 是否过滤QQ机器人消息

# ============ OpenAI 配置 ============
OPENAI_API_KEY = "" 
OPENAI_BASE_URL = "" 
OPENAI_MODEL = "" 

STOPWORDS = set([])
