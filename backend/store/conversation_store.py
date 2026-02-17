# store/conversation_store.py
"""
对话存储类 - 每个对话一个实例
负责单个对话的CRUD操作，包含内存缓存
特点：连接时加载、实时同步、内存缓存读操作
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import uuid

from store.database import Database
from store.utils import json_serializer, now


class ConversationStore:
    """对话存储类 - 每个对话独立实例
    
    每个对话一个实例，包含内存缓存：
    - messages: 内存中的消息列表
    - sections: 内存中的段落列表
    - conversation: 对话基本信息
    
    读写策略：
    - 读操作：直接从内存返回（快）
    - 写操作：同时更新内存和数据库（实时同步）
    - 初始化：从数据库加载到内存（连接时加载）

    已有的基础方法
    - add_message()        # 存消息
    - get_messages()       # 取消息  
    - add_section()        # 存段落
    - update_info()        # 更新状态
    - get_phase()          # 获取当前阶段
    - set_phase()          # 设置阶段
    - generate_report() - 生成完整报告
    - approve_section() - 确认段落
    - edit_section() - 修改段落
    - regenerate_section() - 重写段落
    - get_writing_progress() - 获取写作进度
    """
    @classmethod
    async def create(cls, db: Database, thread_id: str):
        """异步工厂方法：创建实例并加载数据
        
        Args:
            db: 数据库全局单例
            thread_id: 对话ID
            
        Returns:
            已加载数据的 ConversationStore 实例
        """
        instance = cls(db, thread_id)
        await instance.load()  # 调用 load 方法加载数据
        return instance
    
    
    def __init__(self, db: Database, thread_id: str):
        """初始化对话实例
        
        Args:
            db: 数据库全局单例
            thread_id: 对话ID（对应WebSocket的thread_id）
        """
        self.db = db
        self.thread_id = thread_id
        
        # 内存缓存
        self.messages: List[Dict[str, Any]] = []
        self.sections: List[Dict[str, Any]] = []
        self.conversation: Dict[str, Any] = {}
        
        # 初始化时从数据库加载
        # 注意：不能在这里直接 await，需要在外部调用
        # 所以改为由调用者显式调用 load()
        # self._load_from_db()
        
    # ==================== 私有加载方法 ====================
    
    # store/conversation_store.py - 修复 _load_from_db 方法

    async def load(self):
        """显式加载数据（需要在创建后调用）"""
        await self._load_from_db()
        return self

    async def _load_from_db(self):
        """从数据库加载数据到内存（连接时调用）"""
        # 1. 加载对话基本信息
        conv_data = await self.db.get_conversation(self.thread_id)  # 加 await
        print(f"   get_conversation 返回: {conv_data}")
        if conv_data:
            self.conversation = conv_data
            print(f"   找到现有对话: {self.thread_id}")
        else:
            print(f"   没有找到对话，创建新对话: {self.thread_id}")
            # 新对话，创建默认信息
            self.conversation = {
                "id": self.thread_id,
                "title": "新对话",
                "phase": "planning",
                "context": {},
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
             # 保存到数据库，确保后续外键约束通过
            try:
                await self.db.save_conversation_info(self.thread_id, self.conversation)
                print(f"📁 创建新对话记录: {self.thread_id}")
            except Exception as e:
                print(f"❌ 保存新对话记录失败: {e}")
        
        # 2. 加载消息
        self.messages = await self.db.get_messages(self.thread_id)  # 加 await
        
        # 3. 加载段落
        self.sections = await self.db.get_sections(self.thread_id)  # 加 await
        # 4. 最后再次验证对话是否存在（用于调试）
        exists = await self.db.conversation_exists(self.thread_id)
        print(f"  对话是否存在: {exists}")


    # ==================== 对话基本信息操作 ====================
    def get_info(self) -> Dict[str, Any]:
        """获取对话基本信息（从内存）"""
        return self.conversation.copy()
    
    async def update_info(self, **kwargs) -> None:
        """更新对话基本信息
        
        Args:
            **kwargs: 要更新的字段 (phase, title, context)
        """
        if not kwargs:
            return
        
        # 1. 更新内存
        for key, value in kwargs.items():
            if key in ['phase', 'title', 'context']:
                self.conversation[key] = value
        
        self.conversation['updated_at'] = datetime.utcnow()
        
        # 2. 同步到数据库
        await self._sync_conversation_to_db()
    
    async def _sync_conversation_to_db(self):
        """同步对话基本信息到数据库"""
        query = """
        UPDATE conversations 
        SET title = ?, phase = ?, context = ?, updated_at = ?
        WHERE id = ?
        """
        await self.db.execute(
            query,
            [
                self.conversation.get('title', '新对话'),
                self.conversation.get('phase', 'planning'),
                json.dumps(self.conversation.get('context', {}), default=json_serializer),
                self.conversation['updated_at'],
                self.thread_id
            ]
        )
    
    # ==================== 消息操作 ====================
    
    async def add_message(self, message: Dict[str, Any]) -> str:
        """添加消息（同时更新内存和数据库）
        
        Args:
            message: 消息字典，包含 role, content, 可选 id, metadata, created_at
            
        Returns:
            消息ID
        """
        # 1. 生成消息ID（如果没有提供）
        msg_id = message.get('id', str(uuid.uuid4()))
        created_at = message.get('created_at', datetime.utcnow())
        
        # 2. 构建完整消息
        full_message = {
            'id': msg_id,
            'role': message['role'],
            'content': message['content'],
            'created_at': created_at,
            'metadata': message.get('metadata', {})
        }
        
        # 3. 更新内存
        self.messages.append(full_message)
        
        # 4. 更新对话的更新时间（内存）
        self.conversation['updated_at'] = datetime.utcnow()
        
        # 5. 同步到数据库（使用事务保证一致性）
        await self._sync_message_to_db(full_message)
        await self._sync_conversation_to_db()
        
        return msg_id
    
    async def _sync_message_to_db(self, message: Dict[str, Any]):
        """同步单条消息到数据库"""
        query = """
        INSERT INTO messages (id, conversation_id, role, content, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            [
                message['id'],
                self.thread_id,
                message['role'],
                message['content'],
                message['created_at'],
                json.dumps(message['metadata'], default=json_serializer)
            ]
        )
    
    def get_messages(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取消息列表（从内存）
        
        Args:
            limit: 限制返回数量，默认返回全部
            
        Returns:
            消息列表（按时间正序）
        """
        if limit:
            return self.messages[-limit:]
        return self.messages.copy()
    
    def get_recent_messages(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取最近N条消息（用于Agent调用）"""
        return self.messages[-count:]
    
    async def delete_message(self, msg_id: str) -> None:
        """删除消息
        
        Args:
            msg_id: 消息ID
        """
        # 1. 从内存删除
        self.messages = [m for m in self.messages if m['id'] != msg_id]
        
        # 2. 从数据库删除
        query = "DELETE FROM messages WHERE id = ?"
        await self.db.execute(query, [msg_id])
        
        # 3. 更新对话时间
        self.conversation['updated_at'] = datetime.utcnow()
        await self._sync_conversation_to_db()
    
    # ==================== 段落操作 ====================
    
    async def add_section(self, section: Dict[str, Any]) -> str:
        """添加段落（同时更新内存和数据库）
        
        Args:
            section: 段落字典，包含 title, content, 可选 status, order, comments, id
            
        Returns:
            段落ID
        """
        # 1. 生成段落ID
        section_id = section.get('id', str(uuid.uuid4()))
        created_at = section.get('created_at', datetime.utcnow())
        
        # 2. 构建完整段落
        full_section = {
            'id': section_id,
            'title': section['title'],
            'content': section['content'],
            'status': section.get('status', 'draft'),
            'order': section.get('order', len(self.sections)),
            'created_at': created_at,
            'updated_at': datetime.utcnow(),
            'comments': section.get('comments', [])
        }
        
        # 3. 更新内存
        self.sections.append(full_section)
        # 按order排序
        self.sections.sort(key=lambda x: x['order'])
        
        # 4. 更新对话时间
        self.conversation['updated_at'] = datetime.utcnow()
        
        # 5. 同步到数据库
        await self._sync_section_to_db(full_section)
        await self._sync_conversation_to_db()
        
        return section_id
    
    async def _sync_section_to_db(self, section: Dict[str, Any]):
        """同步单条段落到数据库"""
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
                section['id'],
                self.thread_id,
                section['title'],
                section['content'],
                section['status'],
                section['order'],
                section['created_at'],
                section['updated_at'],
                json.dumps(section['comments'], default=json_serializer)
            ]
        )
    
    def get_sections(self) -> List[Dict[str, Any]]:
        """获取所有段落（从内存，按order排序）"""
        return self.sections.copy()
    
    def get_section(self, section_id: str) -> Optional[Dict[str, Any]]:
        """获取指定段落"""
        for section in self.sections:
            if section['id'] == section_id:
                return section.copy()
        return None
    
    async def update_section(self, section_id: str, **kwargs) -> bool:
        """更新段落
        
        Args:
            section_id: 段落ID
            **kwargs: 要更新的字段 (title, content, status, order, comments)
            
        Returns:
            bool: 是否找到并更新
        """
        # 1. 在内存中查找并更新
        found = False
        for section in self.sections:
            if section['id'] == section_id:
                for key, value in kwargs.items():
                    if key in ['title', 'content', 'status', 'order', 'comments']:
                        section[key] = value
                section['updated_at'] = datetime.utcnow()
                found = True
                break
        
        if not found:
            return False
        
        # 2. 重新排序
        self.sections.sort(key=lambda x: x['order'])
        
        # 3. 更新对话时间
        self.conversation['updated_at'] = datetime.utcnow()
        
        # 4. 同步到数据库
        await self._sync_section_update_to_db(section_id, kwargs)
        await self._sync_conversation_to_db()
        
        return True
    
    async def _sync_section_update_to_db(self, section_id: str, updates: Dict[str, Any]):
        """同步段落更新到数据库"""
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
        values.append(datetime.utcnow())
        values.append(section_id)
        
        query = f"UPDATE sections SET {', '.join(sets)} WHERE id = ?"
        await self.db.execute(query, values)
    
    async def update_section_status(self, section_id: str, status: str) -> bool:
        """更新段落状态（常用操作）"""
        return await self.update_section(section_id, status=status)
    
    async def delete_section(self, section_id: str) -> None:
        """删除段落"""
        # 1. 从内存删除
        self.sections = [s for s in self.sections if s['id'] != section_id]
        
        # 2. 重新排序（如果需要）
        for i, section in enumerate(self.sections):
            section['order'] = i
        
        # 3. 从数据库删除
        query = "DELETE FROM sections WHERE id = ?"
        await self.db.execute(query, [section_id])
        
        # 4. 更新对话时间
        self.conversation['updated_at'] = datetime.utcnow()
        await self._sync_conversation_to_db()
    
    # ==================== 完整对话操作 ====================
    
    def to_dict(self) -> Dict[str, Any]:
        """将当前对话转换为字典（用于API返回）"""
        return {
            "id": self.thread_id,
            "title": self.conversation.get('title', '新对话'),
            "phase": self.conversation.get('phase', 'planning'),
            "context": self.conversation.get('context', {}),
            "created_at": self.conversation.get('created_at'),
            "updated_at": self.conversation.get('updated_at'),
            "messages": self.messages,
            "sections": self.sections,
            "message_count": len(self.messages),
            "section_count": len(self.sections)
        }
    
    async def delete_conversation(self) -> None:
        """删除整个对话（级联删除）"""
        # 1. 清空内存
        self.messages = []
        self.sections = []
        self.conversation = {}
        
        # 2. 从数据库删除（外键级联）
        query = "DELETE FROM conversations WHERE id = ?"
        await self.db.execute(query, [self.thread_id])
    
    # ==================== 工具方法 ====================
    
    def is_new(self) -> bool:
        """是否是新对话（没有消息）"""
        return len(self.messages) == 0
    
    def get_phase(self) -> str:
        """获取当前阶段"""
        return self.conversation.get('phase', 'planning')
    
    async def set_phase(self, phase: str) -> None:
        """设置当前阶段"""
        await self.update_info(phase=phase)