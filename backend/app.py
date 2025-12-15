#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask 后端：QQ群年度报告分析器线上版

Licensed under AGPL-3.0: https://www.gnu.org/licenses/agpl-3.0.html

正确流程：
1. 用户上传 → 2. 临时保存 → 3. 后台分析 → 4. 删除临时文件
5. 用户选词 → 6. AI锐评 → 7. 保存MySQL（只存关键数据） → 8. 前端动态渲染
"""

import os
import json
import uuid
import base64
import requests
import asyncio
from typing import List, Dict
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 将根目录加入路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
import analyzer as analyzer_mod
from image_generator import ImageGenerator, AIWordSelector
from utils import load_json

from backend.db_service import DatabaseService
from backend.json_storage import JSONStorageService


app = Flask(__name__)

# CORS配置 - 从环境变量读取
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:5000').split(',')
CORS(app, resources={
    r"/*": {
        "origins": allowed_origins,
        "supports_credentials": True
    }
})

# 文件上传限制 - 从环境变量读取
max_size_mb = int(os.getenv('MAX_UPLOAD_SIZE_MB', '1024'))
app.config['MAX_CONTENT_LENGTH'] = max_size_mb * 1024 * 1024
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-please-change')

# 初始化存储服务（根据配置选择 MySQL 或 JSON）
storage_mode = os.getenv('STORAGE_MODE', 'json').lower()

if storage_mode == 'mysql':
    try:
        print("📦 使用 MySQL 数据库存储")
        db_service = DatabaseService()
        db_service.init_database()
    except Exception as e:
        print(f"⚠️  MySQL 初始化失败: {e}")
        print("🔄 回退到 JSON 文件存储")
        db_service = JSONStorageService()
        db_service.init_database()
else:
    try:
        print("📦 使用 JSON 文件存储（本地模式）")
        db_service = JSONStorageService()
        db_service.init_database()
    except Exception as e:
        print(f"❌ 存储服务初始化失败: {e}")
        db_service = None


def generate_ai_comments(selected_word_objects: List[Dict]) -> Dict[str, str]:
    # 使用OpenAI API为每个热词生成犀利的AI锐评
    # 返回: {word: comment} 的字典
    try:
        from image_generator import AICommentGenerator
        ai_gen = AICommentGenerator()
        
        if ai_gen.client:
            comments = ai_gen.generate_batch(selected_word_objects)
            print("✅ AI锐评生成完成")
            return comments
        else:
            print("⚠️ OpenAI未配置，使用默认锐评")
            return {w['word']: ai_gen._fallback_comment(w['word']) 
                   for w in selected_word_objects}
    except Exception as e:
        print(f"⚠️ AI锐评生成失败: {e}")
        from image_generator import AICommentGenerator
        ai_gen = AICommentGenerator()
        return {w['word']: ai_gen._fallback_comment(w['word']) 
               for w in selected_word_objects}


@app.route("/api/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({
        "ok": True,
        "services": {
            "database": db_service is not None
        }
    })


def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'json'


@app.route("/api/upload", methods=["POST"])
def upload_and_analyze():

    # 步骤1-4: 上传→临时保存→分析→删除临时文件
    # 返回: report_id, 分析结果（热词列表供选择）

    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "缺少文件"}), 400
    
    # 验证文件类型
    if not allowed_file(file.filename):
        return jsonify({"error": "只允许上传JSON文件"}), 400

    # 获取是否AI自动选词
    auto_select = request.form.get("auto_select", "false").lower() == "true"
    
    # 生成report_id
    report_id = str(uuid.uuid4())
    
    # 添加请求日志
    print(f"\n{'='*60}")
    print(f"📤 收到上传请求 | Report ID: {report_id}")
    print(f"   文件名: {file.filename}")
    print(f"   文件大小: {file.content_length or '未知'} 字节")
    print(f"   AI自动选词: {auto_select}")
    print(f"   请求来源: {request.remote_addr}")
    print(f"{'='*60}\n")
    
    # 临时保存文件
    base_dir = os.path.join(PROJECT_ROOT, "runtime_outputs")
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"{report_id}.json")
    file.save(temp_path)

    try:
        # 使用流式解析加载JSON（避免内存溢出）
        data = load_json(temp_path)
        analyzer = analyzer_mod.ChatAnalyzer(data)
        analyzer.analyze()
        report = analyzer.export_json()
        
        # 获取热词列表
        all_words = report.get('topWords', [])[:100]
        
        # 如果是AI自动选词
        if auto_select:
            print("🤖 启动AI智能选词...")
            ai_selector = AIWordSelector()
            
            if ai_selector.client:
                # 使用AI从前200个词中智能选择10个
                selected_word_objects = ai_selector.select_words(all_words, top_n=200)
                
                if selected_word_objects:
                    # 按词频从高到低排序（与手动模式保持一致）
                    selected_word_objects_sorted = sorted(
                        selected_word_objects, 
                        key=lambda w: w['freq'], 
                        reverse=True
                    )
                    selected_words = [w['word'] for w in selected_word_objects_sorted]
                    print(f"✅ AI选词成功（已按词频排序）: {', '.join(selected_words)}")
                else:
                    # AI失败，降级到前10个
                    print("⚠️ AI选词失败，使用前10个热词")
                    selected_words = [w['word'] for w in all_words[:10]]
            else:
                # AI未配置，使用前10个
                print("⚠️ OpenAI未配置，使用前10个热词")
                selected_words = [w['word'] for w in all_words[:10]]
            
            result = finalize_report(
                report_id=report_id,
                analyzer=analyzer,
                selected_words=selected_words,
                auto_mode=True
            )
            # 删除临时文件
            cleanup_temp_files(temp_path)
            return result
        
        # 手动选词模式：返回热词列表，暂存分析结果
        # 将analyzer结果保存到临时文件供后续使用
        result_temp_path = os.path.join(temp_dir, f"{report_id}_result.json")
        with open(result_temp_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 保存analyzer对象到临时文件（使用pickle，以便后续生成群友锐评）
        # 注意：这里只保存analyzer的关键数据，不保存整个对象
        analyzer_data_path = os.path.join(temp_dir, f"{report_id}_analyzer_data.json")
        try:
            # 保存analyzer的关键数据，用于后续生成群友锐评
            analyzer_data = {
                'word_contributors': {
                    word: dict(contributors) 
                    for word, contributors in analyzer.word_contributors.items()
                },
                'user_msg_count': dict(analyzer.user_msg_count),
                'user_char_count': dict(analyzer.user_char_count),
                'user_char_per_msg': analyzer.user_char_per_msg,
                'uin_to_name': analyzer.uin_to_name
            }
            with open(analyzer_data_path, 'w', encoding='utf-8') as f:
                json.dump(analyzer_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存analyzer数据失败: {e}")
        
        return jsonify({
            "report_id": report_id,
            "chat_name": report.get('chatName', '未知群聊'),
            "message_count": report.get('messageCount', 0),
            "available_words": all_words
        })
    except Exception as exc:
        import traceback
        traceback.print_exc()
        # 清理临时文件
        cleanup_temp_files(temp_path)
        return jsonify({"error": f"分析失败: {exc}"}), 500


@app.route("/api/finalize", methods=["POST"])
def finalize_report_endpoint():

    # 步骤5-7: 用户选词 → AI锐评 → 保存MySQL

    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    data = request.json
    report_id = data.get('report_id')
    selected_words = data.get('selected_words', [])
    
    if not report_id or not selected_words:
        return jsonify({"error": "缺少必要参数"}), 400
    
    # 添加请求日志
    print(f"\n{'='*60}")
    print(f"📝 收到选词确认请求 | Report ID: {report_id}")
    print(f"   选中词汇: {', '.join(selected_words[:5])}{'...' if len(selected_words) > 5 else ''}")
    print(f"   词汇数量: {len(selected_words)}")
    print(f"{'='*60}\n")
    
    try:
        # 从临时文件加载分析结果（不需要重新分析！）
        base_dir = os.path.join(PROJECT_ROOT, "runtime_outputs")
        temp_dir = os.path.join(base_dir, "temp")
        result_temp_path = os.path.join(temp_dir, f"{report_id}_result.json")
        analyzer_data_path = os.path.join(temp_dir, f"{report_id}_analyzer_data.json")
        
        if not os.path.exists(result_temp_path):
            return jsonify({"error": "分析结果已过期，请重新上传"}), 404
        
        print("📂 加载已缓存的分析结果...")
        with open(result_temp_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
        
        # 尝试恢复analyzer对象的关键数据，用于生成群友锐评
        restored_analyzer = None
        if os.path.exists(analyzer_data_path):
            try:
                with open(analyzer_data_path, 'r', encoding='utf-8') as f:
                    analyzer_data = json.load(f)
                
                # 创建一个简化的analyzer对象，只包含生成群友锐评需要的数据
                class RestoredAnalyzer:
                    def __init__(self, data):
                        from collections import Counter, defaultdict
                        self.word_contributors = defaultdict(Counter)
                        for word, contributors in data.get('word_contributors', {}).items():
                            self.word_contributors[word] = Counter(contributors)
                        self.user_msg_count = Counter(analyzer_data.get('user_msg_count', {}))
                        self.user_char_count = Counter(analyzer_data.get('user_char_count', {}))
                        self.user_char_per_msg = analyzer_data.get('user_char_per_msg', {})
                        self.uin_to_name = analyzer_data.get('uin_to_name', {})
                    
                    def get_name(self, uin):
                        return self.uin_to_name.get(uin, f"未知用户({uin})")
                    
                    def get_user_representative_words(self, top_n_users=10, words_per_user=5):
                        # 复用analyzer.py中的逻辑
                        from collections import Counter, defaultdict
                        import config as cfg
                        from utils import is_emoji
                        import re
                        
                        user_word_freq = defaultdict(Counter)
                        
                        for word, contributors in self.word_contributors.items():
                            if word in cfg.FUNCTION_WORDS or word in cfg.BLACKLIST:
                                continue
                            if len(word) == 1 and not is_emoji(word):
                                continue
                            
                            for uin, count in contributors.items():
                                if self._is_filtered_user_by_uin(uin):
                                    continue
                                user_word_freq[uin][word] += count
                        
                        top_users = [uin for uin, _ in self.user_msg_count.most_common(top_n_users * 2)]
                        top_users = [uin for uin in top_users if not self._is_filtered_user_by_uin(uin)][:top_n_users]
                        
                        result = []
                        for uin in top_users:
                            user_words = user_word_freq.get(uin, Counter())
                            if not user_words:
                                continue
                            
                            selected_words = []
                            for word, count in user_words.most_common(words_per_user * 3):
                                if word in cfg.FUNCTION_WORDS or word in cfg.BLACKLIST:
                                    continue
                                if len(word) == 1 and not is_emoji(word):
                                    continue
                                if re.match(r'^[\d\W]+$', word) and not is_emoji(word):
                                    continue
                                
                                selected_words.append({'word': word, 'count': count})
                                if len(selected_words) >= words_per_user:
                                    break
                            
                            if not selected_words:
                                continue
                            
                            user_stats = {
                                'message_count': self.user_msg_count.get(uin, 0),
                                'char_count': self.user_char_count.get(uin, 0),
                                'avg_chars_per_msg': self.user_char_per_msg.get(uin, 0)
                            }
                            
                            result.append({
                                'name': self.get_name(uin),
                                'uin': uin,
                                'words': selected_words,
                                'stats': user_stats
                            })
                        
                        return result
                    
                    def _is_filtered_user_by_uin(self, uin):
                        if not uin:
                            return True
                        name = self.uin_to_name.get(uin, '')
                        if not name:
                            return False
                        import config as cfg
                        for filtered_name in cfg.FILTERED_USERS:
                            if filtered_name in name:
                                return True
                        return False
                
                restored_analyzer = RestoredAnalyzer(analyzer_data)
                print("✅ 已恢复analyzer数据，可用于生成群友锐评")
            except Exception as e:
                print(f"⚠️ 恢复analyzer数据失败: {e}")
                import traceback
                traceback.print_exc()

        result = finalize_report(
            report_id=report_id,
            analyzer=restored_analyzer,  
            selected_words=selected_words,
            auto_mode=False,
            report_data=report
        )
        
        # 清理临时文件
        original_json_path = os.path.join(temp_dir, f"{report_id}.json")
        analyzer_data_path = os.path.join(temp_dir, f"{report_id}_analyzer_data.json")
        cleanup_temp_files(result_temp_path)
        cleanup_temp_files(analyzer_data_path)
        if os.path.exists(original_json_path):
            cleanup_temp_files(original_json_path)
        
        return result
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成失败: {exc}"}), 500


def finalize_report(report_id: str, analyzer, selected_words: List[str], 
                   auto_mode: bool = False, report_data: Dict = None):

    # 步骤5-7: 选词 + AI锐评 + 保存MySQL（只存关键数据）

    try:
        if report_data is None:
            report = analyzer.export_json()
        else:
            report = report_data
        
        # 转换selected_words为详细对象
        all_words = {w['word']: w for w in report.get('topWords', [])}
        selected_word_objects = []
        for word in selected_words:
            if word in all_words:
                selected_word_objects.append(all_words[word])
            else:
                selected_word_objects.append({"word": word, "freq": 0, "samples": []})
        
        # 生成AI锐评（传入字典列表）
        ai_comments = generate_ai_comments(selected_word_objects)
        
        # 生成群友性格和用词锐评
        user_personalities = {}
        if analyzer:
            try:
                from image_generator import AIUserPersonalityGenerator
                user_representative_words = analyzer.get_user_representative_words(
                    top_n_users=10, 
                    words_per_user=5
                )
                if user_representative_words:
                    ai_personality_gen = AIUserPersonalityGenerator()
                    if ai_personality_gen.client:
                        user_personalities_comments = ai_personality_gen.generate_batch(user_representative_words)
                        # 转换为字典格式，包含完整信息
                        user_personalities = {
                            u['name']: {
                                'name': u['name'],
                                'uin': u.get('uin', ''),
                                'words': u['words'],
                                'stats': u.get('stats', {}),
                                'personality_comment': user_personalities_comments.get(u['name'], '')
                            }
                            for u in user_representative_words
                        }
                    else:
                        # AI未启用，使用默认锐评
                        user_personalities = {
                            u['name']: {
                                'name': u['name'],
                                'uin': u.get('uin', ''),
                                'words': u['words'],
                                'stats': u.get('stats', {}),
                                'personality_comment': ai_personality_gen._fallback_comment(u['name'], u['words'])
                            }
                            for u in user_representative_words
                        }
            except Exception as e:
                print(f"⚠️ 生成群友锐评失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 提取关键统计数据（只保留前端展示需要的）
        statistics = {
            "chatName": report.get('chatName'),
            "messageCount": report.get('messageCount'),
            "rankings": report.get('rankings', {}),
            "timeDistribution": report.get('timeDistribution', {}),
            "hourDistribution": report.get('hourDistribution', {}),
            "userPersonalities": user_personalities  # 添加群友锐评数据
        }
        
        # 保存到MySQL（只保存关键数据）
        success = db_service.create_report(
            report_id=report_id,
            chat_name=statistics['chatName'],
            message_count=statistics['messageCount'],
            selected_words=selected_word_objects,
            statistics=statistics,
            ai_comments=ai_comments
        )
        
        if not success:
            return jsonify({"error": "保存数据库失败"}), 500
        
        return jsonify({
            "success": True,
            "report_id": report_id,
            "report_url": f"/report/{report_id}",
            "message": "报告已生成" if not auto_mode else "AI已自动完成选词并生成报告"
        })
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"最终化失败: {exc}"}), 500


def cleanup_temp_files(file_path: str):
    """清理临时文件"""
    try:
        # 删除本地临时文件
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ 已删除临时文件: {file_path}")
    except Exception as e:
        print(f"⚠️ 清理临时文件失败: {e}")


@app.route("/api/reports", methods=["GET"])
def list_reports():
    """查询报告列表"""
    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    chat_name = request.args.get('chat_name')
    
    try:
        result = db_service.list_reports(page, page_size, chat_name)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": f"查询失败: {exc}"}), 500


@app.route("/api/templates", methods=["GET"])
def get_templates():
    """获取可用模板列表"""
    import json
    templates_file = os.path.join(PROJECT_ROOT, "frontend/src/templates/templates.json")
    
    try:
        with open(templates_file, 'r', encoding='utf-8') as f:
            templates_data = json.load(f)
            return jsonify(templates_data)
    except Exception as e:
        return jsonify({
            "templates": [
                {
                    "id": "classic",
                    "name": "模板1",
                    "description": "最初的模板",
                    "component": "classic.vue"
                }
            ]
        })


@app.route("/api/reports/<report_id>", methods=["GET"])
def get_report_api(report_id):
    """
    获取报告数据（API接口，返回JSON）
    """
    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    try:
        report = db_service.get_report(report_id)
        if not report:
            return jsonify({"error": "报告不存在"}), 404
        
        # 使用ImageGenerator的数据处理逻辑
        processed_data = process_report_data_for_frontend(report)
        
        return jsonify(processed_data)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"获取失败: {exc}"}), 500


@app.route("/api/reports/<report_id>/personality", methods=["GET"])
def get_personality_report(report_id):
    """
    获取群友性格锐评页面（返回HTML）
    """
    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    try:
        report = db_service.get_report(report_id)
        if not report:
            return jsonify({"error": "报告不存在"}), 404
        
        # 使用ImageGenerator生成群友锐评页面
        from image_generator import ImageGenerator
        
        json_data = {
            'chatName': report['chat_name'],
            'messageCount': report['message_count'],
            'topWords': report['selected_words'],
            'rankings': report['statistics'].get('rankings', {}),
            'hourDistribution': report['statistics'].get('hourDistribution', {})
        }
        
        # 设置输出目录为 runtime_outputs
        base_dir = os.path.join(PROJECT_ROOT, "runtime_outputs")
        gen = ImageGenerator(output_dir=base_dir)
        gen.json_data = json_data
        
        # 从statistics中获取群友锐评数据
        user_personalities_data = report.get('statistics', {}).get('userPersonalities', {})
        if user_personalities_data:
            gen.user_representative_words = [
                {
                    'name': u['name'],
                    'uin': u.get('uin', ''),
                    'words': u.get('words', []),
                    'stats': u.get('stats', {})
                }
                for u in user_personalities_data.values()
            ]
            gen.user_personality_comments = {
                u['name']: u.get('personality_comment', '')
                for u in user_personalities_data.values()
            }
        
        # 生成HTML
        html_path = gen.generate_user_personality_html()
        if not html_path:
            return jsonify({"error": "生成群友锐评页面失败"}), 500
        
        # 读取HTML内容
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        from flask import Response
        return Response(html_content, mimetype='text/html')
        
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"获取失败: {exc}"}), 500


@app.route("/api/reports/<report_id>/personality/image", methods=["POST"])
def generate_personality_image(report_id):
    """
    生成群友性格锐评图片（后端渲染，支持缓存）
    使用HTTP URL + Playwright方式，与年度报告保持一致
    """
    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    try:
        # 获取参数
        data = request.get_json() or {}
        force_regenerate = data.get('force', False)
        image_format = data.get('format', 'for_share')  # for_share 或 for_display
        
        # 检查报告是否存在
        report = db_service.get_report(report_id)
        if not report:
            return jsonify({"error": "报告不存在"}), 404
        
        # 检查缓存
        cache_key = f"personality_{report_id}_{image_format}"
        if not force_regenerate:
            cached_image = db_service.get_cached_image(cache_key)
            if cached_image:
                print(f"📦 返回缓存图片: {cache_key}")
                return jsonify({
                    "success": True,
                    "image_url": cached_image['image_url'],
                    "cached": True,
                    "generated_at": str(cached_image['created_at'])
                })
        
        # 生成新图片
        print(f"🖼️ 开始生成群友分析图片: {report_id} (格式: {image_format})")
        
        # 构建前端URL（使用HTTP访问，与年度报告一致）
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        personality_url = f"{frontend_url}/personality/{report_id}"
        
        # 添加格式参数
        if image_format == 'for_share':
            personality_url += '?mode=share'
        
        # 使用 playwright 生成图片（群友分析使用1000px宽度，避免触发媒体查询的单列布局）
        # 注意：页面内容宽度是900px，但视口需要>950px才能保持两列布局
        # 使用device_scale_factor=3提高清晰度（与image_generator.py中的设置一致）
        image_data = asyncio.run(generate_image_with_playwright(
            personality_url, 
            viewport_width=1000,  # 设置为1000px，大于950px媒体查询断点，确保两列布局
            viewport_height=1200, 
            device_scale_factor=3  # 提高到3倍，确保高清截图
        ))
        
        if not image_data:
            return jsonify({"error": "图片生成失败"}), 500
        
        # 保存到缓存
        image_url = db_service.save_image_cache(cache_key, image_data)
        
        print(f"✅ 群友分析图片生成成功: {cache_key}")
        
        return jsonify({
            "success": True,
            "image_url": image_url,
            "cached": False,
            "generated_at": "now"
        })
        
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成失败: {exc}"}), 500


@app.route("/api/reports/<report_id>", methods=["DELETE"])
def delete_report(report_id):
    """删除报告"""
    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    try:
        success = db_service.delete_report(report_id)
        if not success:
            return jsonify({"error": "报告不存在"}), 404
        
        return jsonify({"success": True, "message": "报告已删除"})
    except Exception as exc:
        return jsonify({"error": f"删除失败: {exc}"}), 500


@app.route("/api/reports/<report_id>/generate-image", methods=["POST"])
def generate_report_image(report_id):
    """
    生成报告图片（后端渲染，支持缓存）
    
    Query参数：
    - template: 模板ID（默认classic）
    - force: 是否强制重新生成（默认false）
    - format: 图片格式，可选 for_display（网页显示版）或 for_share（分享版，默认）
    """
    if not db_service:
        return jsonify({"error": "数据库服务未初始化"}), 500
    
    try:
        # 获取参数
        data = request.get_json() or {}
        template_id = data.get('template', 'classic')
        force_regenerate = data.get('force', False)
        image_format = data.get('format', 'for_share')  # for_share 或 for_display
        
        # 检查报告是否存在
        report = db_service.get_report(report_id)
        if not report:
            return jsonify({"error": "报告不存在"}), 404
        
        # 检查缓存
        cache_key = f"{report_id}_{template_id}_{image_format}"
        if not force_regenerate:
            cached_image = db_service.get_cached_image(cache_key)
            if cached_image:
                print(f"📦 返回缓存图片: {cache_key}")
                return jsonify({
                    "success": True,
                    "image_url": cached_image['image_url'],
                    "cached": True,
                    "generated_at": str(cached_image['created_at'])
                })
        
        # 生成新图片
        print(f"🖼️ 开始生成图片: {report_id} (模板: {template_id}, 格式: {image_format})")
        
        # 构建前端URL
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        report_url = f"{frontend_url}/report/{template_id}/{report_id}"
        
        # 添加格式参数
        if image_format == 'for_share':
            report_url += '?mode=share'
        
        # 使用 playwright 生成图片（年度报告使用450px宽度）
        image_data = asyncio.run(generate_image_with_playwright(
            report_url,
            viewport_width=450,
            viewport_height=800,
            device_scale_factor=2
        ))
        
        if not image_data:
            return jsonify({"error": "图片生成失败"}), 500
        
        # 保存到缓存
        image_url = db_service.save_image_cache(cache_key, image_data)
        
        print(f"✅ 图片生成成功: {cache_key}")
        
        return jsonify({
            "success": True,
            "image_url": image_url,
            "cached": False,
            "generated_at": "now"
        })
        
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成失败: {exc}"}), 500


async def generate_image_with_playwright(url, viewport_width=450, viewport_height=800, device_scale_factor=2):
    """
    使用 Playwright 无头浏览器生成图片
    返回 base64 编码的图片数据
    
    Args:
        url: 要访问的URL
        viewport_width: 视口宽度（默认450，群友分析使用900）
        viewport_height: 视口高度（默认800）
        device_scale_factor: 设备缩放因子（默认2）
    """
    # 强制布局的JavaScript代码（用于群友分析的两列布局）
    force_layout_js = """
        () => {
            try {
                const body = document.body;
                const reportContainer = document.querySelector('.report-container');
                const personalityContent = document.querySelector('.personality-content');
                const userSection = document.querySelector('.user-section');
                
                if (body) {
                    body.style.width = '900px';
                    body.style.maxWidth = '900px';
                }
                if (reportContainer) {
                    reportContainer.style.width = '900px';
                    reportContainer.style.maxWidth = '900px';
                }
                if (personalityContent) {
                    personalityContent.style.maxWidth = '900px';
                    personalityContent.style.width = '900px';
                }
                if (userSection) {
                    userSection.style.display = 'grid';
                    userSection.style.gridTemplateColumns = '1fr 1fr';
                }
                return true;
            } catch (e) {
                console.error('Force layout error:', e);
                return false;
            }
        }
    """
    
    # #region agent log
    import json
    import os
    log_path = r'g:\git\QQgroup-annual-report-analyzer\.cursor\debug.log'
    def debug_log(location, message, data, hypothesis_id):
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'sessionId': 'debug-session',
                    'runId': 'run1',
                    'hypothesisId': hypothesis_id,
                    'location': location,
                    'message': message,
                    'data': data,
                    'timestamp': __import__('time').time() * 1000
                }, ensure_ascii=False) + '\n')
                f.flush()
        except Exception as e:
            print(f"DEBUG LOG ERROR: {e}")
    debug_log('app.py:813', 'generate_image_with_playwright called', {'url': url, 'viewport_width': viewport_width, 'viewport_height': viewport_height}, 'A')
    # #endregion
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 需要安装 Playwright: pip install playwright && playwright install chromium")
        return None
    
    try:
        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            # 创建页面，设置视口和设备缩放
            # 注意：对于群友分析（900px），需要确保视口宽度足够大，避免触发媒体查询
            page = await browser.new_page(
                viewport={'width': viewport_width, 'height': viewport_height},
                device_scale_factor=device_scale_factor
            )
            
            # #region agent log
            debug_log('app.py:840', 'Page created with viewport', {'viewport_width': viewport_width, 'viewport_height': viewport_height}, 'C')
            # #endregion
            
            # 设置用户代理，确保CSS媒体查询正确工作
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            print(f"   🌐 访问: {url} (视口宽度: {viewport_width}px)")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # #region agent log
            actual_viewport = await page.evaluate('() => ({width: window.innerWidth, height: window.innerHeight})')
            debug_log('app.py:851', 'After page.goto - actual viewport', actual_viewport, 'C')
            # #endregion
            
            # 确保视口宽度正确（特别是对于群友分析的900px）
            await page.set_viewport_size({'width': viewport_width, 'height': viewport_height})
            
            # #region agent log
            actual_viewport_after = await page.evaluate('() => ({width: window.innerWidth, height: window.innerHeight})')
            debug_log('app.py:854', 'After set_viewport_size - actual viewport', actual_viewport_after, 'C')
            # #endregion
            
            # 等待内容渲染
            await page.wait_for_timeout(3000)
            
            # 对于群友分析（viewport_width >= 900），强制覆盖CSS以确保两列布局
            if viewport_width >= 900:
                try:
                    result = await page.evaluate(force_layout_js)
                    if result:
                        print(f"   🔧 强制布局设置成功")
                    await page.wait_for_timeout(500)
                except Exception as e:
                    print(f"   ⚠️ 强制布局设置失败: {e}")
                    await page.wait_for_timeout(500)
                
                # #region agent log
                forced_layout = await page.evaluate("""
                    () => {
                        const body = document.body;
                        const reportContainer = document.querySelector('.report-container');
                        const userSection = document.querySelector('.user-section');
                        return {
                            bodyWidth: body.offsetWidth,
                            containerWidth: reportContainer?.offsetWidth || 0,
                            userSectionGrid: userSection ? window.getComputedStyle(userSection).gridTemplateColumns : 'none'
                        };
                    }
                """)
                debug_log('app.py:875', 'After forcing layout - dimensions', forced_layout, 'A')
                print(f"   🔧 强制布局后 - Body宽度: {forced_layout.get('bodyWidth')}px, 容器宽度: {forced_layout.get('containerWidth')}px, Grid: {forced_layout.get('userSectionGrid')}")
                # #endregion
            
            # 验证布局是否正确（对于群友分析，检查是否为两列）
            if viewport_width >= 900:
                layout_check = await page.evaluate("""
                    () => {
                        const userSection = document.querySelector('.user-section');
                        const body = document.body;
                        const reportContainer = document.querySelector('.report-container');
                        const personalityContent = document.querySelector('.personality-content');
                        
                        if (userSection) {
                            const computedStyle = window.getComputedStyle(userSection);
                            const bodyStyle = window.getComputedStyle(body);
                            const containerStyle = reportContainer ? window.getComputedStyle(reportContainer) : null;
                            const contentStyle = personalityContent ? window.getComputedStyle(personalityContent) : null;
                            
                            const gridColumns = computedStyle.gridTemplateColumns;
                            const display = computedStyle.display;
                            const viewportWidth = window.innerWidth;
                            const containerWidth = reportContainer?.offsetWidth || 0;
                            const bodyWidth = body.offsetWidth;
                            const contentWidth = personalityContent?.offsetWidth || 0;
                            
                            // 检查媒体查询是否匹配
                            const mediaQuery = window.matchMedia('(max-width: 950px)');
                            
                            return {
                                hasUserSection: true,
                                display: display,
                                gridColumns: gridColumns,
                                viewportWidth: viewportWidth,
                                containerWidth: containerWidth,
                                bodyWidth: bodyWidth,
                                contentWidth: contentWidth,
                                bodyMaxWidth: bodyStyle.maxWidth,
                                containerMaxWidth: containerStyle?.maxWidth || 'none',
                                contentMaxWidth: contentStyle?.maxWidth || 'none',
                                mediaQueryMatches: mediaQuery.matches,
                                isTwoColumn: gridColumns.includes('1fr 1fr') || (gridColumns.split(' ').length >= 2 && !gridColumns.includes('1fr'))
                            };
                        }
                        return { hasUserSection: false };
                    }
                """)
                print(f"   📐 布局检查: {layout_check}")
                
                # #region agent log
                debug_log('app.py:861', 'Layout check result', layout_check, 'A')
                debug_log('app.py:861', 'Layout check result', layout_check, 'B')
                debug_log('app.py:861', 'Layout check result', layout_check, 'D')
                debug_log('app.py:861', 'Layout check result', layout_check, 'E')
                # #endregion
                
                if layout_check.get('hasUserSection'):
                    if layout_check.get('isTwoColumn'):
                        print(f"   ✅ 确认: 群友分析页面已正确显示为两列布局")
                    else:
                        print(f"   ⚠️ 警告: 群友分析页面未显示为两列布局")
                        print(f"      视口宽度: {layout_check.get('viewportWidth')}px")
                        print(f"      容器宽度: {layout_check.get('containerWidth')}px")
                        print(f"      Body宽度: {layout_check.get('bodyWidth')}px")
                        print(f"      Content宽度: {layout_check.get('contentWidth')}px")
                        print(f"      媒体查询匹配: {layout_check.get('mediaQueryMatches')}")
                        print(f"      Grid列设置: {layout_check.get('gridColumns')}")
                        print(f"      显示模式: {layout_check.get('display')}")
            
            # 等待所有图片加载完成
            await page.evaluate("""
                async () => {
                    const images = Array.from(document.images);
                    const promises = images.map((img) => {
                        return new Promise((resolve) => {
                            if (img.complete && img.naturalHeight !== 0) {
                                resolve();
                                return;
                            }
                            img.onload = () => resolve();
                            img.onerror = () => resolve();  // 失败也继续
                            setTimeout(() => resolve(), 5000);  // 超时保护
                        });
                    });
                    await Promise.all(promises);
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
            """)
            
            # 隐藏保存按钮（如果存在）
            await page.evaluate("""
                () => {
                    const saveButton = document.querySelector('.save-button');
                    if (saveButton) {
                        saveButton.style.display = 'none';
                    }
                }
            """)
            
            # 等待布局稳定（特别是grid布局）
            await page.wait_for_timeout(1000)
            
            # 获取实际高度（只计算实际内容的高度，不包括多余的空白）
            height = await page.evaluate("""
                () => {
                    // 获取report-container的实际内容高度（这是实际内容区域）
                    const reportContainer = document.querySelector('.report-container');
                    if (reportContainer) {
                        // 获取容器内最后一个有内容的元素
                        const children = Array.from(reportContainer.children);
                        let lastElement = null;
                        for (let i = children.length - 1; i >= 0; i--) {
                            const elem = children[i];
                            // 跳过隐藏元素和空白元素
                            const style = window.getComputedStyle(elem);
                            if (style.display !== 'none' && style.visibility !== 'hidden' && elem.offsetHeight > 0) {
                                lastElement = elem;
                                break;
                            }
                        }
                        
                        if (lastElement) {
                            // 计算从容器顶部到最后一个元素底部的距离
                            const containerTop = reportContainer.offsetTop;
                            const lastElementBottom = lastElement.offsetTop + lastElement.offsetHeight;
                            const contentHeight = lastElementBottom - containerTop + 50; // 加50px底部边距
                            return contentHeight;
                        }
                        
                        // 如果没有找到最后一个元素，使用容器的scrollHeight
                        return reportContainer.scrollHeight;
                    }
                    
                    // 如果没有report-container，使用body的高度
                    const bodyHeight = document.body.scrollHeight;
                    const docHeight = document.documentElement.scrollHeight;
                    return Math.min(bodyHeight, docHeight); // 取较小值，避免多余空白
                }
            """)
            
            print(f"   📏 页面内容高度: {height}px")
            
            # 设置视口高度，只设置必要的高度，避免多余空白
            await page.set_viewport_size({'width': viewport_width, 'height': min(height + 50, 5000)})  # 限制最大高度，避免过大
            
            # 对于群友分析，重新强制设置布局（因为set_viewport_size可能触发重新布局）
            if viewport_width >= 900:
                await page.evaluate("""
                    () => {
                        const body = document.body;
                        const reportContainer = document.querySelector('.report-container');
                        const personalityContent = document.querySelector('.personality-content');
                        const userSection = document.querySelector('.user-section');
                        
                        if (body) {
                            body.style.width = '900px';
                            body.style.maxWidth = '900px';
                        }
                        if (reportContainer) {
                            reportContainer.style.width = '900px';
                            reportContainer.style.maxWidth = '900px';
                        }
                        if (personalityContent) {
                            personalityContent.style.maxWidth = '900px';
                            personalityContent.style.width = '900px';
                        }
                        if (userSection) {
                            userSection.style.display = 'grid';
                            userSection.style.gridTemplateColumns = '1fr 1fr';
                        }
                    }
                """)
            
            # 再次等待布局稳定
            await page.wait_for_timeout(1000)
            
            # 滚动到页面底部，确保所有内容都已渲染（特别是grid布局）
            await page.evaluate("""
                () => {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            await page.wait_for_timeout(500)
            
            # 滚动回顶部
            await page.evaluate("""
                () => {
                    window.scrollTo(0, 0);
                }
            """)
            await page.wait_for_timeout(500)
            
            # 再次获取高度（滚动后可能发生变化，但只计算实际内容）
            final_height = await page.evaluate("""
                () => {
                    const reportContainer = document.querySelector('.report-container');
                    if (reportContainer) {
                        const children = Array.from(reportContainer.children);
                        let lastElement = null;
                        for (let i = children.length - 1; i >= 0; i--) {
                            const elem = children[i];
                            const style = window.getComputedStyle(elem);
                            if (style.display !== 'none' && style.visibility !== 'hidden' && elem.offsetHeight > 0) {
                                lastElement = elem;
                                break;
                            }
                        }
                        
                        if (lastElement) {
                            const containerTop = reportContainer.offsetTop;
                            const lastElementBottom = lastElement.offsetTop + lastElement.offsetHeight;
                            return lastElementBottom - containerTop + 50;
                        }
                        return reportContainer.scrollHeight;
                    }
                    return Math.min(document.body.scrollHeight, document.documentElement.scrollHeight);
                }
            """)
            
            if final_height > height:
                print(f"   📏 更新后内容高度: {final_height}px")
                await page.set_viewport_size({'width': viewport_width, 'height': min(final_height + 50, 5000)})
                
                # 再次强制设置布局（因为set_viewport_size可能触发重新布局）
                if viewport_width >= 900:
                    try:
                        await page.evaluate(force_layout_js)
                    except Exception as e:
                        print(f"   ⚠️ 更新后强制布局失败: {e}")
                
                await page.wait_for_timeout(500)
            
            # 截图前最后一次强制设置布局，确保万无一失
            if viewport_width >= 900:
                await page.evaluate("""
                    () => {
                        const body = document.body;
                        const reportContainer = document.querySelector('.report-container');
                        const personalityContent = document.querySelector('.personality-content');
                        const userSection = document.querySelector('.user-section');
                        
                        if (body) {
                            body.style.width = '900px';
                            body.style.maxWidth = '900px';
                        }
                        if (reportContainer) {
                            reportContainer.style.width = '900px';
                            reportContainer.style.maxWidth = '900px';
                        }
                        if (personalityContent) {
                            personalityContent.style.maxWidth = '900px';
                            personalityContent.style.width = '900px';
                        }
                        if (userSection) {
                            userSection.style.display = 'grid';
                            userSection.style.gridTemplateColumns = '1fr 1fr';
                        }
                    }
                """)
                await page.wait_for_timeout(200)
            
            # 截图前最后一次计算精确的内容高度
            screenshot_info = await page.evaluate("""
                () => {
                    const reportContainer = document.querySelector('.report-container');
                    if (reportContainer) {
                        // 找到容器内最后一个可见元素
                        const children = Array.from(reportContainer.children);
                        let lastElement = null;
                        let maxBottom = 0;
                        
                        for (let i = 0; i < children.length; i++) {
                            const elem = children[i];
                            const style = window.getComputedStyle(elem);
                            if (style.display !== 'none' && style.visibility !== 'hidden' && elem.offsetHeight > 0) {
                                const rect = elem.getBoundingClientRect();
                                const bottom = rect.bottom + window.scrollY;
                                if (bottom > maxBottom) {
                                    maxBottom = bottom;
                                    lastElement = elem;
                                }
                            }
                        }
                        
                        if (lastElement) {
                            // 计算从页面顶部到最后一个元素底部的距离
                            const containerRect = reportContainer.getBoundingClientRect();
                            const containerTop = containerRect.top + window.scrollY;
                            const lastElementRect = lastElement.getBoundingClientRect();
                            const lastElementBottom = lastElementRect.bottom + window.scrollY;
                            
                            // 加上一些底部边距
                            const footer = document.querySelector('.footer') || document.querySelector('footer');
                            const footerHeight = footer ? footer.getBoundingClientRect().height : 0;
                            
                            const contentHeight = lastElementBottom - containerTop + footerHeight + 20; // 20px底部边距
                            return {
                                height: Math.ceil(contentHeight),
                                containerTop: Math.ceil(containerTop),
                                lastElementBottom: Math.ceil(lastElementBottom)
                            };
                        }
                        
                        return {
                            height: reportContainer.scrollHeight,
                            containerTop: 0,
                            lastElementBottom: reportContainer.scrollHeight
                        };
                    }
                    
                    // 如果没有容器，使用body的实际内容高度
                    const body = document.body;
                    const html = document.documentElement;
                    return {
                        height: Math.min(body.scrollHeight, html.scrollHeight),
                        containerTop: 0,
                        lastElementBottom: Math.min(body.scrollHeight, html.scrollHeight)
                    };
                }
            """)
            
            # 安全获取截图高度
            if screenshot_info and isinstance(screenshot_info, dict):
                screenshot_height = screenshot_info.get('height', final_height if 'final_height' in locals() else viewport_height)
            else:
                screenshot_height = final_height if 'final_height' in locals() else viewport_height
            
            # 确保高度有效
            if screenshot_height <= 0:
                screenshot_height = viewport_height
            if screenshot_height > 10000:  # 限制最大高度，避免过大
                screenshot_height = 10000
            
            print(f"   📏 精确截图高度: {screenshot_height}px")
            
            # 截图前再次检查布局
            # #region agent log
            if viewport_width >= 900:
                try:
                    final_check = await page.evaluate("""
                        () => {
                            const userSection = document.querySelector('.user-section');
                            if (userSection) {
                                const style = window.getComputedStyle(userSection);
                                return {
                                    gridColumns: style.gridTemplateColumns,
                                    viewportWidth: window.innerWidth,
                                    containerWidth: document.querySelector('.report-container')?.offsetWidth || 0
                                };
                            }
                            return null;
                        }
                    """)
                    debug_log('app.py:965', 'Before screenshot - final layout check', final_check, 'A')
                except:
                    pass
            # #endregion
            
            # 设置视口高度为精确的内容高度（限制最大高度）
            actual_screenshot_height = min(int(screenshot_height), 5000)
            if actual_screenshot_height < 100:
                actual_screenshot_height = viewport_height  # 如果太小，使用默认高度
            
            await page.set_viewport_size({'width': viewport_width, 'height': actual_screenshot_height})
            await page.wait_for_timeout(300)
            
            # 滚动到顶部，确保从顶部开始截图
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(200)
            
            # 截图 - 使用full_page=False，只截取视口内容（已设置为精确高度）
            # 确保高质量截图
            try:
                screenshot_bytes = await page.screenshot(
                    full_page=False,  # 不使用full_page，只截取当前视口
                    type='png'
                    # PNG格式不支持quality参数，移除它
                )
            except Exception as e:
                print(f"   ⚠️ 截图失败，尝试使用full_page模式: {e}")
                # 如果失败，回退到full_page模式
                screenshot_bytes = await page.screenshot(
                    full_page=True,
                    type='png'
                )
            
            # #region agent log
            debug_log('app.py:970', 'Screenshot taken', {'size_bytes': len(screenshot_bytes)}, 'A')
            # #endregion
            
            await browser.close()
            
            # 转换为 base64
            image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # #region agent log
            debug_log('app.py:978', 'Function exit', {'image_b64_length': len(image_b64)}, 'A')
            # #endregion
            
            return f"data:image/png;base64,{image_b64}"
            
    except Exception as e:
        print(f"❌ Playwright 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_report_data_for_frontend(report):
    """
    使用ImageGenerator的逻辑处理报告数据为前端需要的格式
    复用image_generator.py中的_prepare_template_data方法
    """

    json_data = {
        'chatName': report['chat_name'],
        'messageCount': report['message_count'],
        'topWords': report['selected_words'],  # 这里已经包含完整的词信息
        'rankings': report['statistics'].get('rankings', {}),
        'hourDistribution': report['statistics'].get('hourDistribution', {})
    }
    

    gen = ImageGenerator()
    gen.json_data = json_data
    gen.selected_words = report['selected_words']  
    gen.ai_comments = report.get('ai_comments', {}) or {}
    
    # 从statistics中获取群友锐评数据
    user_personalities_data = report.get('statistics', {}).get('userPersonalities', {})
    if user_personalities_data:
        # 转换为列表格式
        gen.user_representative_words = [
            {
                'name': u['name'],
                'uin': u.get('uin', ''),
                'words': u.get('words', []),
                'stats': u.get('stats', {})
            }
            for u in user_personalities_data.values()
        ]
        gen.user_personality_comments = {
            u['name']: u.get('personality_comment', '')
            for u in user_personalities_data.values()
        }
    
    # 调用其数据处理方法
    template_data = gen._prepare_template_data()
    
    # 返回前端需要的格式，确保AI评语被正确包含
    return {
        "report_id": report['report_id'],
        "chat_name": template_data['chat_name'],
        "message_count": template_data['message_count'],
        "selected_words": template_data['selected_words'],  # 这里已经包含ai_comment
        "rankings": template_data['rankings'],  # 这里已经是处理好的榜单
        "champion": template_data.get('champion'),  # 群神人信息
        "statistics": {
            "hourDistribution": {str(h['hour']): h['count'] for h in template_data['hour_data']}
        },
        "peak_hour": template_data['peak_hour'],
        "user_personalities": template_data.get('user_personalities', []),  # 群友性格锐评
        "created_at": str(report['created_at'])
    }


# 静态文件服务 - 用于 Docker 部署时提供前端页面
frontend_dist = os.path.join(PROJECT_ROOT, "frontend", "dist")

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """提供前端静态文件服务"""
    if path and os.path.exists(os.path.join(frontend_dist, path)):
        return send_from_directory(frontend_dist, path)
    # 默认返回 index.html（用于 Vue Router）
    return send_from_directory(frontend_dist, "index.html")


if __name__ == "__main__":
    debug_mode = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    base_port = int(os.environ.get("FLASK_PORT", os.environ.get("PORT", 5000)))

    def try_run(p):
        app.run(host="0.0.0.0", port=p, debug=debug_mode, use_reloader=False)

    try:
        try_run(base_port)
    except OSError as exc:
        if "Address already in use" in str(exc):
            fallback = base_port + 1
            print(f"⚠️ 端口 {base_port} 已被占用，尝试 {fallback}")
            try_run(fallback)
        else:
            raise
