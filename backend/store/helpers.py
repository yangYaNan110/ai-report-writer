"""
数据库辅助函数
"""
import json
from datetime import datetime
from typing import Optional, Any
from store.database import db

def now() -> str:
    """获取当前ISO格式时间"""
    return datetime.now().isoformat()

def to_json(obj: Any) -> str:
    """对象转JSON字符串"""
    return json.dumps(obj, ensure_ascii=False, default=str)

def from_json(json_str: str) -> Any:
    """JSON字符串转对象"""
    return json.loads(json_str)

class ConversationStore:
    """对话存储 - 原生SQL实现"""
    
    async def create(self, thread_id: str, title: str, initial_state: dict) -> dict:
        """创建新对话"""
        state = initial_state.copy()
        state["thread_id"] = thread_id
        state["title"] = title
        state["created_at"] = now()
        state["updated_at"] = now()
        
        await db.execute(
            """
            INSERT INTO conversations (thread_id, title, state_json, phase, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                title,
                to_json(state),
                state.get("phase", "planning"),
                state["created_at"],
                state["updated_at"]
            )
        )
        return state
    
    async def load(self, thread_id: str) -> Optional[dict]:
        """加载对话"""
        result = await db.fetch_one(
            "SELECT state_json FROM conversations WHERE thread_id = ?",
            (thread_id,)
        )
        if result:
            return from_json(result["state_json"])
        return None
    
    async def save(self, thread_id: str, state: dict):
        """保存状态"""
        state["updated_at"] = now()
        await db.execute(
            """
            UPDATE conversations 
            SET state_json = ?, phase = ?, updated_at = ?
            WHERE thread_id = ?
            """,
            (to_json(state), state.get("phase", "planning"), state["updated_at"], thread_id)
        )
    
    async def list(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """获取对话列表（只返回元数据）"""
        results = await db.fetch_all(
            """
            SELECT thread_id, title, phase, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        return results
    
    async def delete(self, thread_id: str) -> bool:
        """删除对话"""
        cursor = await db.execute(
            "DELETE FROM conversations WHERE thread_id = ?",
            (thread_id,)
        )
        return cursor.rowcount > 0