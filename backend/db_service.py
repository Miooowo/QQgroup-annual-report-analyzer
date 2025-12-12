#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库服务：管理报告数据的存储和查询
只存储关键展示数据，前端动态渲染
"""

import pymysql
import json
import os
import sys
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()


class DatabaseService:
    def __init__(self):
        # 从环境变量读取配置
        self.config = {
            'host': os.getenv('MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'user': os.getenv('MYSQL_USER', 'root'),
            'password': os.getenv('MYSQL_PASSWORD', ''),
            'database': os.getenv('MYSQL_DATABASE', 'qq_reports'),
            'charset': os.getenv('MYSQL_CHARSET', 'utf8mb4')
        }
    
    def get_connection(self):
        """获取数据库连接"""
        return pymysql.connect(**self.config)
    
    def init_database(self):
        """初始化数据库和表结构"""
        conn = None
        try:
            config_without_db = self.config.copy()
            database_name = config_without_db.pop('database')
            conn = pymysql.connect(**config_without_db)
            cursor = conn.cursor()
            
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE {database_name}")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    report_id VARCHAR(64) UNIQUE NOT NULL COMMENT '报告唯一ID',
                    chat_name VARCHAR(255) NOT NULL COMMENT '群聊名称',
                    message_count INT NOT NULL COMMENT '消息总数',
                    
                    selected_words JSON NOT NULL COMMENT '选中的热词列表（包含word, freq, samples, contributors等）',
                    statistics JSON NOT NULL COMMENT '关键统计数据（rankings, timeDistribution等）',
                    ai_comments JSON COMMENT 'AI锐评内容 {word: comment}',
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    
                    INDEX idx_chat_name (chat_name),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            conn.commit()
            print("✅ 数据库初始化成功")
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def create_report(self, report_id: str, chat_name: str, message_count: int,
                     selected_words: List[Dict], statistics: Dict, 
                     ai_comments: Optional[Dict] = None) -> bool:
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            sql = """
                INSERT INTO reports 
                (report_id, chat_name, message_count, selected_words, statistics, ai_comments)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                report_id,
                chat_name,
                message_count,
                json.dumps(selected_words, ensure_ascii=False),
                json.dumps(statistics, ensure_ascii=False),
                json.dumps(ai_comments, ensure_ascii=False) if ai_comments else None
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"创建报告失败: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            sql = "SELECT * FROM reports WHERE report_id = %s"
            cursor.execute(sql, (report_id,))
            result = cursor.fetchone()
            
            if result:
                # 解析JSON字段
                if result.get('selected_words'):
                    result['selected_words'] = json.loads(result['selected_words'])
                if result.get('statistics'):
                    result['statistics'] = json.loads(result['statistics'])
                if result.get('ai_comments'):
                    result['ai_comments'] = json.loads(result['ai_comments'])
            
            return result
        except Exception as e:
            print(f"获取报告失败: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def list_reports(self, page: int = 1, page_size: int = 20, 
                    chat_name: Optional[str] = None) -> Dict[str, Any]:
        """分页查询报告列表"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            
            # 构建查询条件
            where_clause = ""
            params = []
            if chat_name:
                where_clause = "WHERE chat_name LIKE %s"
                params.append(f"%{chat_name}%")
            
            # 查询总数
            count_sql = f"SELECT COUNT(*) as total FROM reports {where_clause}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()['total']
            
            # 查询数据
            offset = (page - 1) * page_size
            data_sql = f"""
                SELECT id, report_id, chat_name, message_count, 
                       created_at, updated_at
                FROM reports 
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(data_sql, params + [page_size, offset])
            data = cursor.fetchall()
            
            return {
                'data': data,
                'total': total,
                'page': page,
                'page_size': page_size
            }
        except Exception as e:
            print(f"查询报告列表失败: {e}")
            return {'data': [], 'total': 0, 'page': page, 'page_size': page_size}
        finally:
            if conn:
                conn.close()
    
    def delete_report(self, report_id: str) -> bool:
        """删除报告"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            sql = "DELETE FROM reports WHERE report_id = %s"
            cursor.execute(sql, (report_id,))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"删除报告失败: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
