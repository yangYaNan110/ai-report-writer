"""
数据库连接配置 - 使用原生SQL
阶段3.2：完善表结构，支持对话、消息、段落存储
"""
import aiosqlite
import json
from typing import Optional, Any, List
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
        
        # 连接时自动初始化表结构
        await self._init_tables()
    
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
    
    async def fetch_all(self, sql: str, params: tuple = ()) -> List[dict]:
        """查询多条记录"""
        if not self.connection:
            await self.connect()
        cursor = await self.connection.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]
    
    async def execute_many(self, sql: str, params_list: List[tuple]) -> aiosqlite.Cursor:
        """批量执行SQL"""
        if not self.connection:
            await self.connect()
        cursor = await self.connection.executemany(sql, params_list)
        await self.connection.commit()
        return cursor
    
    async def execute_transaction(self, sql_statements: List[tuple]):
        """执行事务（多条SQL语句）
        
        Args:
            sql_statements: 列表，每个元素是 (sql, params) 的元组
        """
        if not self.connection:
            await self.connect()
        
        try:
            # 开始事务
            await self.connection.execute("BEGIN TRANSACTION")
            
            for sql, params in sql_statements:
                await self.connection.execute(sql, params)
            
            # 提交事务
            await self.connection.commit()
        except Exception as e:
            # 回滚事务
            await self.connection.rollback()
            raise e
    
    async def _init_tables(self):
        """初始化数据库表结构（内部调用）"""
        
        # 开发环境：直接删除旧表重建
        # 注意：这会丢失所有数据，仅适合开发阶段
        print("🔄 重建数据库表结构...")
        
        # 删除旧表（注意顺序，因为有外键约束）
        await self.execute("DROP TABLE IF EXISTS sections")
        await self.execute("DROP TABLE IF EXISTS messages")
        await self.execute("DROP TABLE IF EXISTS conversations")
        
        # 创建conversations表（新结构）
        await self.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                phase TEXT NOT NULL,
                context TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)
        
        # 创建messages表（新结构）
        await self.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                metadata TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        
        # 创建sections表（新结构）
        await self.execute("""
            CREATE TABLE IF NOT EXISTS sections (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                "order" INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                comments TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        
        # 创建索引...
        # ... 索引代码同上
        
        print("✅ 数据库表结构重建完成")

# 创建全局数据库实例
db = Database()

async def init_db():
    """初始化数据库（兼容旧代码）"""
    if not db.connection:
        await db.connect()
    # _init_tables 已经在 connect 中调用，这里不再重复
    print("✅ 数据库初始化完成")


async def get_db() -> Database:
    """获取数据库连接的依赖函数"""
    try:
        if not db.connection:
            await db.connect()
        yield db
    finally:
        # 注意：这里不断开连接，让连接池管理
        pass

# store/database.py（在现有代码后面添加）

if __name__ == "__main__":
    """命令行测试
    使用方法：
        python store/database.py
    """
    import asyncio
    import sys
    
    async def test_connection():
        """测试数据库连接和建表"""
        print("=" * 50)
        print("🧪 测试数据库连接和建表")
        print("=" * 50)
        
        # 1. 连接数据库
        print("\n1. 连接数据库...")
        await db.connect()
        
        # 2. 验证表是否存在
        print("\n2. 验证表结构...")
        tables = await db.fetch_all("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('conversations', 'messages', 'sections')
        """)
        
        table_names = [t['name'] for t in tables]
        print(f"   存在的表: {table_names}")
        
        expected_tables = {'conversations', 'messages', 'sections'}
        if set(table_names) == expected_tables:
            print("   ✅ 所有表创建成功")
        else:
            missing = expected_tables - set(table_names)
            print(f"   ❌ 缺少表: {missing}")
        
        # 3. 查看表结构
        print("\n3. 表结构详情:")
        for table in ['conversations', 'messages', 'sections']:
            print(f"\n   📋 {table} 表:")
            columns = await db.fetch_all(f"PRAGMA table_info({table})")
            for col in columns:
                print(f"      - {col['name']}: {col['type']}")
        
        # 4. 查看索引
        print("\n4. 索引详情:")
        indexes = await db.fetch_all("""
            SELECT name, tbl_name FROM sqlite_master 
            WHERE type='index' AND tbl_name IN ('conversations', 'messages', 'sections')
        """)
        for idx in indexes:
            print(f"      - {idx['tbl_name']}: {idx['name']}")
        
        # 5. 测试外键约束
        print("\n5. 测试外键约束...")
        fk_status = await db.fetch_one("PRAGMA foreign_keys")
        print(f"   外键约束: {'✅ 启用' if fk_status['foreign_keys'] else '❌ 未启用'}")
        
        # 6. 关闭连接
        await db.close()
        print("\n✅ 测试完成，连接已关闭")
    
    # 运行测试
    asyncio.run(test_connection())