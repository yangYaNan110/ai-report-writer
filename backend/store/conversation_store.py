# store/conversation_store.py
"""
对话存储类
负责 Conversation 对象的CRUD操作
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import uuid

from store.database import Database
from store.utils import json_serializer, now

class ConversationStore:
    """对话存储类
    
    职责：
    - 对话的创建、读取、更新、删除
    - 消息的添加和查询
    - 段落的添加和更新
    """
    
    def __init__(self, db: Database):
        self.db = db
    
    # ==================== 对话主表操作 ====================
    
    async def create_conversation(self, conv_id: str, title: str = "") -> None:
        """创建新对话
        
        Args:
            conv_id: 对话ID（对应WebSocket的thread_id）
            title: 对话标题（可选）
        """
        query = """
        INSERT INTO conversations (id, title, phase, context, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            [
                conv_id,
                title or "新对话",
                "planning",  # 默认从规划阶段开始
                json.dumps({}, default=json_serializer),  # 空context
                now(),
                now()
            ]
        )
    
    async def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """获取对话基本信息
        
        Args:
            conv_id: 对话ID
            
        Returns:
            对话字典，不存在返回None
        """
        query = "SELECT * FROM conversations WHERE id = ?"
        row = await self.db.fetch_one(query, [conv_id])
        if row:
            # 解析JSON字段
            if row.get('context'):
                row['context'] = json.loads(row['context'])
        return row
    
    async def update_conversation(self, conv_id: str, **kwargs) -> None:
        """更新对话字段
        
        Args:
            conv_id: 对话ID
            **kwargs: 要更新的字段 (phase, title, context)
        """
        if not kwargs:
            return
            
        sets = []
        values = []
        for key, value in kwargs.items():
            if key in ['phase', 'title', 'context']:
                sets.append(f"{key} = ?")
                if key == 'context':
                    values.append(json.dumps(value, default=json_serializer))
                else:
                    values.append(str(value))
        
        if not sets:
            return
            
        sets.append("updated_at = ?")
        values.append(now())
        values.append(conv_id)
        
        query = f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?"
        await self.db.execute(query, values)
    
    async def delete_conversation(self, conv_id: str) -> None:
        """删除对话（级联删除相关消息和段落）
        
        Args:
            conv_id: 对话ID
        """
        # 由于设置了外键 ON DELETE CASCADE，只需删除主表记录
        query = "DELETE FROM conversations WHERE id = ?"
        await self.db.execute(query, [conv_id])
    
    async def list_conversations(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取对话列表（按更新时间倒序）
        
        Args:
            limit: 返回数量
            offset: 偏移量（用于分页）
            
        Returns:
            对话列表
        """
        query = """
        SELECT id, title, phase, created_at, updated_at 
        FROM conversations 
        ORDER BY updated_at DESC 
        LIMIT ? OFFSET ?
        """
        rows = await self.db.fetch_all(query, [limit, offset])
        return rows
    
    # ==================== 消息操作 ====================
    
    async def add_message(self, conv_id: str, message: Dict[str, Any]) -> str:
        """添加消息
        
        Args:
            conv_id: 对话ID
            message: 消息字典，包含 role, content, 可选 id, metadata
            
        Returns:
            消息ID
        """
        # 生成消息ID（如果没有提供）
        msg_id = message.get('id', str(uuid.uuid4()))
        
        query = """
        INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            [
                msg_id,
                conv_id,
                message['role'],
                message['content'],
                message.get('created_at', now()),
                json.dumps(message.get('metadata', {}), default=json_serializer)
            ]
        )
        
        # 更新对话的更新时间
        await self.update_conversation(conv_id)
        
        return msg_id
    
    async def get_messages(self, conv_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取对话的消息列表
        
        Args:
            conv_id: 对话ID
            limit: 返回最新多少条消息
            
        Returns:
            消息列表（按时间正序）
        """
        query = """
        SELECT * FROM messages 
        WHERE conversation_id = ? 
        ORDER BY created_at ASC 
        LIMIT ?
        """
        rows = await self.db.fetch_all(query, [conv_id, limit])
        
        # 解析JSON字段
        for row in rows:
            if row.get('metadata'):
                row['metadata'] = json.loads(row['metadata'])
        
        return rows
    
    async def delete_message(self, msg_id: str) -> None:
        """删除消息
        
        Args:
            msg_id: 消息ID
        """
        query = "DELETE FROM messages WHERE id = ?"
        await self.db.execute(query, [msg_id])
    
    # ==================== 段落操作 ====================
    
    async def add_section(self, conv_id: str, section: Dict[str, Any]) -> str:
        """添加段落
        
        Args:
            conv_id: 对话ID
            section: 段落字典，包含 title, content, status, order, 可选 id, comments
            
        Returns:
            段落ID
        """
        # 生成段落ID（如果没有提供）
        section_id = section.get('id', str(uuid.uuid4()))
        
        query = """
        INSERT INTO sections (
            id, conversation_id, title, content, status, "order", 
            created_at, updated_at, comments
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            [
                section_id,
                conv_id,
                section['title'],
                section['content'],
                section.get('status', 'draft'),
                section.get('order', 0),
                section.get('created_at', now()),
                now(),
                json.dumps(section.get('comments', []), default=json_serializer)
            ]
        )
        
        # 更新对话的更新时间
        await self.update_conversation(conv_id)
        
        return section_id
    
    async def get_sections(self, conv_id: str) -> List[Dict[str, Any]]:
        """获取对话的所有段落
        
        Args:
            conv_id: 对话ID
            
        Returns:
            段落列表（按order排序）
        """
        query = """
        SELECT * FROM sections 
        WHERE conversation_id = ? 
        ORDER BY "order" ASC
        """
        rows = await self.db.fetch_all(query, [conv_id])
        
        # 解析JSON字段
        for row in rows:
            if row.get('comments'):
                row['comments'] = json.loads(row['comments'])
        
        return rows
    
    async def update_section(self, section_id: str, **kwargs) -> None:
        """更新段落
        
        Args:
            section_id: 段落ID
            **kwargs: 要更新的字段 (title, content, status, order, comments)
        """
        if not kwargs:
            return
            
        sets = []
        values = []
        for key, value in kwargs.items():
            if key in ['title', 'content', 'status', 'order', 'comments']:
                sets.append(f"{key} = ?")
                if key == 'comments':
                    values.append(json.dumps(value, default=json_serializer))
                else:
                    values.append(value)
        
        if not sets:
            return
            
        sets.append("updated_at = ?")
        values.append(now())
        values.append(section_id)
        
        query = f"UPDATE sections SET {', '.join(sets)} WHERE id = ?"
        await self.db.execute(query, values)
    
    async def delete_section(self, section_id: str) -> None:
        """删除段落
        
        Args:
            section_id: 段落ID
        """
        query = "DELETE FROM sections WHERE id = ?"
        await self.db.execute(query, [section_id])
    
    async def update_section_status(self, section_id: str, status: str) -> None:
        """更新段落状态（常用操作，单独封装）
        
        Args:
            section_id: 段落ID
            status: 新状态 (draft/pending/confirmed/rejected)
        """
        await self.update_section(section_id, status=status)
    
    # ==================== 完整对话操作 ====================
    
    async def load_full_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """加载完整对话（包含消息和段落）
        
        Args:
            conv_id: 对话ID
            
        Returns:
            完整对话字典，包含 messages 和 sections 字段
        """
        # 获取对话基本信息
        conversation = await self.get_conversation(conv_id)
        if not conversation:
            return None
        
        # 获取消息列表
        messages = await self.get_messages(conv_id)
        
        # 获取段落列表
        sections = await self.get_sections(conv_id)
        
        # 组装完整对话
        conversation['messages'] = messages
        conversation['sections'] = sections
        
        return conversation
    
    async def save_full_conversation(self, conversation: Dict[str, Any]) -> None:
        """保存完整对话（使用事务）
        
        Args:
            conversation: 完整对话字典，包含 id, messages, sections 等
        """
        conv_id = conversation['id']
        
        # 准备事务语句
        statements = []
        
        # 1. 保存或更新对话主表
        existing = await self.get_conversation(conv_id)
        if existing:
            # 更新
            statements.append((
                """
                UPDATE conversations 
                SET title = ?, phase = ?, context = ?, updated_at = ?
                WHERE id = ?
                """,
                [
                    conversation['title'],
                    conversation['phase'],
                    json.dumps(conversation.get('context', {}), default=json_serializer),
                    now(),
                    conv_id
                ]
            ))
        else:
            # 插入
            statements.append((
                """
                INSERT INTO conversations (id, title, phase, context, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    conv_id,
                    conversation['title'],
                    conversation['phase'],
                    json.dumps(conversation.get('context', {}), default=json_serializer),
                    conversation.get('created_at', now()),
                    now()
                ]
            ))
        
        # 2. 先删除旧的消息和段落（简单方式：全删重建）
        statements.append(("DELETE FROM messages WHERE conversation_id = ?", [conv_id]))
        statements.append(("DELETE FROM sections WHERE conversation_id = ?", [conv_id]))
        
        # 3. 插入新消息
        for msg in conversation.get('messages', []):
            statements.append((
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    msg.get('id', str(uuid.uuid4())),
                    conv_id,
                    msg['role'],
                    msg['content'],
                    msg.get('created_at', now()),
                    json.dumps(msg.get('metadata', {}), default=json_serializer)
                ]
            ))
        
        # 4. 插入新段落
        for section in conversation.get('sections', []):
            statements.append((
                """
                INSERT INTO sections (
                    id, conversation_id, title, content, status, "order", 
                    created_at, updated_at, comments
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    section.get('id', str(uuid.uuid4())),
                    conv_id,
                    section['title'],
                    section['content'],
                    section.get('status', 'draft'),
                    section.get('order', 0),
                    section.get('created_at', now()),
                    now(),
                    json.dumps(section.get('comments', []), default=json_serializer)
                ]
            ))
        
        # 执行事务
        await self.db.execute_transaction(statements)