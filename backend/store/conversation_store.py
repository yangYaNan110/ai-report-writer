# store/conversation_store.py
"""
对话存储类
负责 Conversation 对象的CRUD操作
"""
from typing import Optional, List
from datetime import datetime
import json

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
    
    async def get_conversation(self, conv_id: str) -> Optional[dict]:
        """获取对话基本信息
        
        Args:
            conv_id: 对话ID
            
        Returns:
            对话字典，不存在返回None
        """
        query = "SELECT * FROM conversations WHERE id = ?"
        rows = await self.db.fetch_all(query, [conv_id])
        return rows[0] if rows else None
    
    async def update_conversation(self, conv_id: str, **kwargs) -> None:
        """更新对话字段
        
        Args:
            conv_id: 对话ID
            **kwargs: 要更新的字段（如 phase, title, context）
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
                    values.append(value)
        
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