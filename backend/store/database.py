"""
数据库连接配置 - 使用原生SQL
阶段0：SQLite基础配置
"""
import aiosqlite
import json
from typing import Optional, Any
import os
from datetime import datetime

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'conversations.db')

class Database:
    """数据库连接管理器 - 原生SQL版本"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """建立数据库连接"""
        # 确保data目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.connection = await aiosqlite.connect(self.db_path)
        # 启用外键约束
        await self.connection.execute("PRAGMA foreign_keys = ON")
        # 返回行作为类字典对象
        self.connection.row_factory = aiosqlite.Row
        print(f"✅ 数据库连接成功: {self.db_path}")
    
    async def close(self):
        """关闭数据库连接"""
        if self.connection:
            await self.connection.close()
            self.connection = None
    
    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """执行SQL语句（不返回结果）"""
        if not self.connection:
            await self.connect()
        cursor = await self.connection.execute(sql, params)
        await self.connection.commit()
        return cursor
    
    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """查询单条记录"""
        if not self.connection:
            await self.connect()
        cursor = await self.connection.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return dict(row)
        return None
    
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """查询多条记录"""
        if not self.connection:
            await self.connect()
        cursor = await self.connection.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]
    
    async def execute_many(self, sql: str, params_list: list[tuple]) -> aiosqlite.Cursor:
        """批量执行SQL"""
        if not self.connection:
            await self.connect()
        cursor = await self.connection.executemany(sql, params_list)
        await self.connection.commit()
        return cursor

# 创建全局数据库实例
db = Database()

async def init_db():
    """初始化数据库，创建表"""
    # 创建conversations表
    await db.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            thread_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            state_json TEXT NOT NULL,  -- 存储完整的ConversationState JSON
            phase TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    
    # 创建索引
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_updated 
        ON conversations(updated_at DESC)
    """)
    
    # 创建messages表（可选，用于单独查询消息）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            type TEXT NOT NULL,
            section_id TEXT,
            timestamp TIMESTAMP NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES conversations(thread_id) ON DELETE CASCADE
        )
    """)
    
    # 创建索引
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_thread_timestamp 
        ON messages(thread_id, timestamp DESC)
    """)
    
    print("✅ 数据库表初始化完成")

async def get_db() -> Database:
    """获取数据库连接的依赖函数"""
    try:
        if not db.connection:
            await db.connect()
        yield db
    finally:
        # 注意：这里不断开连接，让连接池管理
        pass