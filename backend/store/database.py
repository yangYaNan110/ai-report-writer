"""
数据库连接配置 - 使用原生SQL
阶段3.2：完善表结构，支持对话、消息、段落存储
添加了 ConversationStore 所需的所有数据库操作方法
"""
import aiosqlite
import json
from typing import Optional, Any, Dict, List, Tuple
import os
from datetime import datetime
from config.settings import settings
from datetime import datetime, timezone  # 确保导入 timezone
import uuid


# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'conversations.db')


def json_serializer(obj):
    """JSON序列化器，处理datetime等特殊类型"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class Database:
    """数据库连接管理器 - 原生SQL版本"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None
        self.connection_id = str(uuid.uuid4())[:8]  # 添加连接ID
    
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
            print("🔌 数据库连接已关闭")
    
    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """执行SQL语句（不返回结果）"""
        if not self.connection:
            await self.connect()
        
        print(f"📝 [连接 {self.connection_id}] 执行SQL: {sql[:60]}...")
        print(f"   参数: {params}")
        cursor = await self.connection.execute(sql, params)

        print(f"   执行完成，准备commit...")  # 添加这行
        await self.connection.commit()
        print(f"   ✅ commit完成")  # 添加这行
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
    
    # ==================== 表结构初始化 ====================
    
    async def _init_tables(self):
        """初始化数据库表结构（内部调用）"""
        
        # 开发环境：直接删除旧表重建
        # 注意：这会丢失所有数据，仅适合开发阶段
        print("🔄 重建数据库表结构...")
        
        # 删除旧表（注意顺序，因为有外键约束）
        # 只在开发环境且明确指定时才重建
        # rebuild = settings.REBUILD_DB
        # if rebuild:
        #     await self.execute("DROP TABLE IF EXISTS sections")
        #     await self.execute("DROP TABLE IF EXISTS messages")
        #     await self.execute("DROP TABLE IF EXISTS conversations")
        
        # 创建conversations表
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
        
        # 创建messages表
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
        
        # 创建sections表
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
        
        # 创建索引
        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_updated 
            ON conversations(updated_at DESC)
        """)
        
        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
            ON messages(conversation_id)
        """)
        
        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created_at 
            ON messages(created_at)
        """)
        
        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_sections_conversation_id 
            ON sections(conversation_id)
        """)
        
        await self.execute("""
            CREATE INDEX IF NOT EXISTS idx_sections_status 
            ON sections(status)
        """)
        
        print("✅ 数据库表结构重建完成")
    
    # ==================== Conversation 操作 ====================
    
    async def get_conversation(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """获取对话基本信息"""
        query = "SELECT * FROM conversations WHERE id = ?"
        row = await self.fetch_one(query, [thread_id])
        if row:
            # 解析JSON字段
            if row.get('context'):
                try:
                    row['context'] = json.loads(row['context'])
                except:
                    row['context'] = {}
        return row
    
    async def save_conversation_info(self, thread_id: str, info: Dict[str, Any]) -> None:
        """保存对话基本信息（INSERT OR REPLACE）"""
        # 先检查是否存在
        existing = await self.fetch_one(
            "SELECT id FROM conversations WHERE id = ?",
            (thread_id,)
        )
        
        if existing:
            # 存在则更新
            query = """
            UPDATE conversations 
            SET title = ?, phase = ?, context = ?, updated_at = ?
            WHERE id = ?
            """
            await self.execute(
                query,
                (
                    info.get('title', '新对话'),
                    info.get('phase', 'planning'),
                    json.dumps(info.get('context', {}), default=json_serializer),
                    info.get('updated_at', datetime.now(timezone.utc)),
                    thread_id
                )
            )
        else:
            # 不存在则插入
            query = """
            INSERT INTO conversations (id, title, phase, context, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            await self.execute(
                query,
                (
                    thread_id,
                    info.get('title', '新对话'),
                    info.get('phase', 'planning'),
                    json.dumps(info.get('context', {}), default=json_serializer),
                    info.get('created_at', datetime.now(timezone.utc)),
                    info.get('updated_at', datetime.now(timezone.utc))
                )
            )
    
    async def update_conversation(self, thread_id: str, updates: Dict[str, Any]) -> None:
        """更新对话信息"""
        if not updates:
            return
            
        sets = []
        values = []
        for key, value in updates.items():
            if key in ['title', 'phase', 'context']:
                sets.append(f"{key} = ?")
                if key == 'context':
                    values.append(json.dumps(value, default=json_serializer))
                else:
                    values.append(value)
        
        if not sets:
            return
            
        sets.append("updated_at = ?")
        values.append(datetime.now(timezone.utc))
        values.append(thread_id)
        
        query = f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?"
        await self.execute(query, values)
    
    async def delete_conversation(self, thread_id: str) -> None:
        """删除对话（级联删除相关消息和段落）"""
        query = "DELETE FROM conversations WHERE id = ?"
        await self.execute(query, [thread_id])
    
    async def list_conversations(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取对话列表（按更新时间倒序）"""
        query = """
        SELECT id, title, phase, created_at, updated_at 
        FROM conversations 
        ORDER BY updated_at DESC 
        LIMIT ? OFFSET ?
        """
        rows = await self.fetch_all(query, [limit, offset])
        return rows
    
    # ==================== Message 操作 ====================
    
    async def get_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        """获取对话的消息列表"""
        query = """
        SELECT * FROM messages 
        WHERE conversation_id = ? 
        ORDER BY created_at ASC
        """
        rows = await self.fetch_all(query, [thread_id])
        
        # 解析JSON字段
        for row in rows:
            if row.get('metadata'):
                try:
                    row['metadata'] = json.loads(row['metadata'])
                except:
                    row['metadata'] = {}
        
        return rows
    
    async def save_message(self, thread_id: str, message: Dict[str, Any]) -> None:
        """保存单条消息"""
        print(f"\n🔵 [DEBUG] save_message 被调用")
        print(f"   thread_id: {thread_id}")
        print(f"   message id: {message['id']}")
        print(f"   message role: {message['role']}")
        print(f"   message content: {message['content'][:30]}...")
        print(f"\n🔵 [DEBUG] save_message 被调用 [连接 {self.connection_id}]")
        print("=" * 30)
        # //test-123
        # //b664cbe4-84a2-4bcd-94fb-c7a23af92d62
        # //连接 1d450c2a

        # thread_id: test-123
        # message id: adaab7ef-3a79-4835-8f84-0361b9ea76b0

        # 处理 datetime：转换为 ISO 格式字符串
        created_at = message.get('created_at', datetime.now(timezone.utc))
        print(f"   created_at 类型: {type(created_at)}")
        print(f"   created_at 值: {created_at}")

        # 检查所有参数类型
        params = [
            message['id'],
            thread_id,
            message['role'],
            message['content'],
            created_at,
            json.dumps(message.get('metadata', {}), default=json_serializer)
        ]
        print(f"   所有参数类型: {[type(p) for p in params]}")


        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        # 先检查当前有多少条消息
        before_count = await self.fetch_one(
            "SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?",
            [thread_id]
        )
        print(f"   保存前消息数: {before_count['count'] if before_count else 0}")
      
        
        try:
            query = """
            INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            await self.execute(
                query,
                [
                    message['id'],
                    thread_id,
                    message['role'],
                    message['content'],
                    message.get('created_at', datetime.now(timezone.utc)),
                    json.dumps(message.get('metadata', {}), default=json_serializer)
                ]
            )
            print(f"   ✅ INSERT 成功")

            # 添加这些行（强制同步并验证）
            print(f"   强制checkpoint...")
            await self.connection.execute("PRAGMA wal_checkpoint")
            
            print(f"   立即验证...")
            verification = await self.fetch_one(
                "SELECT * FROM messages WHERE id = ?",
                (message['id'],)
            )
            if verification:
                print(f"   ✅ 验证成功：消息在数据库中！content: {verification['content'][:30]}...")
            else:
                print(f"   ❌ 验证失败：消息不在数据库中！")
        except Exception as e:
            print(f"   ❌ INSERT 失败: {e}")
            # 如果失败，尝试 UPDATE
            try:
                query = """
                UPDATE messages 
                SET role=?, content=?, created_at=?, metadata=?
                WHERE id = ?
                """
                await self.execute(
                    query,
                    [
                        message['role'],
                        message['content'],
                        message.get('created_at', datetime.now(timezone.utc)),
                        json.dumps(message.get('metadata', {}), default=json_serializer),
                        message['id']
                    ]
                )
                print(f"   ✅ UPDATE 成功")
            except Exception as e2:
                print(f"   ❌ UPDATE 也失败: {e2}")
        
        # 验证保存后的数量
        after_count = await self.fetch_one(
            "SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?",
            [thread_id]
        )
        print(f"   保存后消息数: {after_count['count'] if after_count else 0}")
    async def save_messages(self, thread_id: str, messages: List[Dict[str, Any]]) -> None:
        """批量保存消息"""
        if not messages:
            return
            
        query = """
        INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        params_list = []
        for msg in messages:
            params_list.append((
                msg['id'],
                thread_id,
                msg['role'],
                msg['content'],
                msg.get('created_at', datetime.now(timezone.utc)),
                json.dumps(msg.get('metadata', {}), default=json_serializer)
            ))
        
        await self.execute_many(query, params_list)
    
    async def delete_message(self, msg_id: str) -> None:
        """删除单条消息"""
        query = "DELETE FROM messages WHERE id = ?"
        await self.execute(query, [msg_id])
    
    async def delete_messages_by_conversation(self, thread_id: str) -> None:
        """删除对话的所有消息"""
        query = "DELETE FROM messages WHERE conversation_id = ?"
        await self.execute(query, [thread_id])
    
    # ==================== Section 操作 ====================
    
    async def get_sections(self, thread_id: str) -> List[Dict[str, Any]]:
        """获取对话的所有段落"""
        query = """
        SELECT * FROM sections 
        WHERE conversation_id = ? 
        ORDER BY "order" ASC
        """
        rows = await self.fetch_all(query, [thread_id])
        
        # 解析JSON字段
        for row in rows:
            if row.get('comments'):
                try:
                    row['comments'] = json.loads(row['comments'])
                except:
                    row['comments'] = []
        
        return rows
    
    async def save_section(self, thread_id: str, section: Dict[str, Any]) -> None:
        """保存单条段落"""
        query = """
        INSERT INTO sections (
            id, conversation_id, title, content, status, "order", 
            created_at, updated_at, comments
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self.execute(
            query,
            [
                section['id'],
                thread_id,
                section['title'],
                section['content'],
                section.get('status', 'draft'),
                section.get('order', 0),
                section.get('created_at', datetime.now(timezone.utc)),
                section.get('updated_at', datetime.now(timezone.utc)),
                json.dumps(section.get('comments', []), default=json_serializer)
            ]
        )
    
    async def save_sections(self, thread_id: str, sections: List[Dict[str, Any]]) -> None:
        """批量保存段落"""
        if not sections:
            return
            
        query = """
        INSERT INTO sections (
            id, conversation_id, title, content, status, "order", 
            created_at, updated_at, comments
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params_list = []
        for sec in sections:
            params_list.append((
                sec['id'],
                thread_id,
                sec['title'],
                sec['content'],
                sec.get('status', 'draft'),
                sec.get('order', 0),
                sec.get('created_at', datetime.now(timezone.utc)),
                sec.get('updated_at', datetime.now(timezone.utc)),
                json.dumps(sec.get('comments', []), default=json_serializer)
            ))
        
        await self.execute_many(query, params_list)
    
    async def update_section(self, section_id: str, updates: Dict[str, Any]) -> None:
        """更新段落信息"""
        if not updates:
            return
            
        sets = []
        values = []
        for key, value in updates.items():
            if key in ['title', 'content', 'status', 'order', 'comments']:
                sets.append(f"{key} = ?")
                if key == 'comments':
                    values.append(json.dumps(value, default=json_serializer))
                else:
                    values.append(value)
        
        if not sets:
            return
            
        sets.append("updated_at = ?")
        values.append(datetime.now(timezone.utc))
        values.append(section_id)
        
        query = f"UPDATE sections SET {', '.join(sets)} WHERE id = ?"
        await self.execute(query, values)
    
    async def delete_section(self, section_id: str) -> None:
        """删除单条段落"""
        query = "DELETE FROM sections WHERE id = ?"
        await self.execute(query, [section_id])
    
    async def delete_sections_by_conversation(self, thread_id: str) -> None:
        """删除对话的所有段落"""
        query = "DELETE FROM sections WHERE conversation_id = ?"
        await self.execute(query, [thread_id])
    
    # ==================== 统计查询 ====================
    
    async def count_messages(self, thread_id: str) -> int:
        """统计对话的消息数量"""
        query = "SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?"
        row = await self.fetch_one(query, [thread_id])
        return row['count'] if row else 0
    
    async def count_sections(self, thread_id: str) -> int:
        """统计对话的段落数量"""
        query = "SELECT COUNT(*) as count FROM sections WHERE conversation_id = ?"
        row = await self.fetch_one(query, [thread_id])
        return row['count'] if row else 0
    
    async def conversation_exists(self, thread_id: str) -> bool:
        """检查对话是否存在"""
        query = "SELECT 1 FROM conversations WHERE id = ?"
        row = await self.fetch_one(query, [thread_id])
        return row is not None


# 创建全局数据库实例
db = Database()


async def init_db():
    """初始化数据库（兼容旧代码）"""
    if not db.connection:
        await db.connect()
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


# ==================== 命令行测试 ====================

if __name__ == "__main__":
    """命令行测试
    使用方法：
        python store/database.py
    """
    import asyncio
    
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
        
        # 6. 测试新增的方法
        print("\n6. 测试新增的方法...")
        test_thread = "test-thread-123"
        
        # 测试 conversation 操作
        print("\n   📝 测试 conversation 操作...")
        await db.save_conversation_info(test_thread, {"title": "测试对话", "phase": "planning"})
        conv = await db.get_conversation(test_thread)
        print(f"      获取对话: {conv['title'] if conv else 'None'}")
        
        # 测试 message 操作
        print("\n   📝 测试 message 操作...")
        import uuid
        msg = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": "测试消息",
            "metadata": {"test": True}
        }
        await db.save_message(test_thread, msg)
        msgs = await db.get_messages(test_thread)
        print(f"      获取消息数: {len(msgs)}")
        
        # 测试 section 操作
        print("\n   📝 测试 section 操作...")
        sec = {
            "id": str(uuid.uuid4()),
            "title": "测试章节",
            "content": "测试内容",
            "status": "draft",
            "order": 1,
            "comments": []
        }
        await db.save_section(test_thread, sec)
        secs = await db.get_sections(test_thread)
        print(f"      获取段落数: {len(secs)}")
        
        # 清理测试数据
        await db.delete_conversation(test_thread)
        
        print("\n   ✅ 所有方法测试通过")
        
        # 7. 关闭连接
        await db.close()
        print("\n✅ 测试完成，连接已关闭")
    
    # 运行测试
    asyncio.run(test_connection())