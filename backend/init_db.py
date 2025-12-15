#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
"""

import pymysql
from dotenv import load_dotenv
import os

load_dotenv()


def init_database():
    """初始化数据库和表"""
    host = os.getenv('MYSQL_HOST', 'localhost')
    port = int(os.getenv('MYSQL_PORT', 3306))
    user = os.getenv('MYSQL_USER', 'root')
    password = os.getenv('MYSQL_PASSWORD', '')
    database = os.getenv('MYSQL_DATABASE', 'qq_reports')
    
    print(f"连接到 MySQL 服务器 {host}:{port}...")
    
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset='utf8mb4'
    )
    
    try:
        with conn.cursor() as cursor:
            print(f"创建数据库 {database}...")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"✓ 数据库 {database} 已创建或已存在")
            
            cursor.execute(f"USE {database}")
            
            print("删除旧表（如果存在）...")
            cursor.execute("DROP TABLE IF EXISTS reports")
            print("✓ 旧表已删除")
            
            print("创建报告表...")
            cursor.execute("""
                CREATE TABLE reports (
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
            print("✓ 报告表已创建")
            
            conn.commit()
            print("\n✅ 数据库初始化完成！")
            
    finally:
        conn.close()


if __name__ == '__main__':
    try:
        init_database()
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        exit(1)
