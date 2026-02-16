"""
会话管理器
负责管理WebSocket连接、消息发送、断线重连基础功能

阶段3.3
"""
from typing import Dict, Optional, List
from fastapi import WebSocket
import asyncio
from loguru import logger
from datetime import datetime
import json

from store.conversation_store import ConversationStore
from models.events import ServerEvent, EventType
from models.state import Phase


class SessionManager:
    """会话管理器
    
    职责：
    - 管理活跃的WebSocket连接
    - 连接/断开事件处理
    - 消息发送（单发/广播）
    - 为断线重连做准备（阶段6）
    """
    
    def __init__(self, store: ConversationStore):
        # thread_id -> WebSocket 映射
        self.active_connections: Dict[str, WebSocket] = {}
        # thread_id -> 最后活动时间
        self.last_activity: Dict[str, datetime] = {}
        # 消息队列（用于断线重连时缓存消息）
        self.pending_messages: Dict[str, List[dict]] = {}
        
        self.store = store
        logger.info("🚀 SessionManager 初始化完成")
    
    async def connect(self, thread_id: str, websocket: WebSocket) -> bool:
        """新WebSocket连接建立
        
        Args:
            thread_id: 对话ID
            websocket: WebSocket连接对象
            
        Returns:
            bool: 是否成功
        """
        try:
            # 1. 接受WebSocket连接
            await websocket.accept()
            
            # 2. 检查是否有旧连接
            if thread_id in self.active_connections:
                old_ws = self.active_connections[thread_id]
                logger.warning(f"🔌 检测到重复连接，关闭旧连接: {thread_id}")
                try:
                    await old_ws.close(code=1000, reason="新连接建立")
                except:
                    pass
            
            # 3. 保存新连接
            self.active_connections[thread_id] = websocket
            self.last_activity[thread_id] = datetime.utcnow()
            
            # 4. 初始化消息队列（如果不存在）
            if thread_id not in self.pending_messages:
                self.pending_messages[thread_id] = []
            
            logger.info(f"🔌 新连接建立: {thread_id}, 当前连接数: {len(self.active_connections)}")
            
            # 5. 发送连接成功事件
            await self.send_event(thread_id, {
                "type": EventType.SYNC,
                "data": {
                    "status": "connected",
                    "message": "连接成功"
                }
            })
            
            # 6. 加载历史对话并发送（如果有）
            await self._load_and_send_history(thread_id)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 连接建立失败 {thread_id}: {str(e)}")
            return False
    
    async def disconnect(self, thread_id: str, code: int = 1000, reason: str = "正常断开"):
        """连接断开
        
        Args:
            thread_id: 对话ID
            code: 断开代码
            reason: 断开原因
        """
        try:
            # 1. 关闭WebSocket连接（如果还在）
            if thread_id in self.active_connections:
                ws = self.active_connections[thread_id]
                try:
                    await ws.close(code=code, reason=reason)
                except:
                    pass
                
                # 2. 从活跃连接中移除
                del self.active_connections[thread_id]
                
                # 3. 更新最后活动时间
                if thread_id in self.last_activity:
                    del self.last_activity[thread_id]
                
                logger.info(f"🔌 连接断开: {thread_id}, 剩余连接数: {len(self.active_connections)}")
            
        except Exception as e:
            logger.error(f"❌ 断开连接失败 {thread_id}: {str(e)}")
    
    async def send_message(self, thread_id: str, message: dict) -> bool:
        """发送消息给指定对话
        
        Args:
            thread_id: 对话ID
            message: 消息内容（符合ServerEvent格式）
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 1. 检查连接是否存在
            if thread_id not in self.active_connections:
                # 连接不存在，缓存消息（用于断线重连）
                self.pending_messages[thread_id].append({
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                })
                logger.debug(f"📨 连接不存在，消息已缓存: {thread_id}")
                return False
            
            # 2. 获取WebSocket连接
            websocket = self.active_connections[thread_id]
            
            # 3. 添加时间戳（如果没有）
            if "timestamp" not in message:
                message["timestamp"] = datetime.utcnow().isoformat()
            
            # 4. 发送消息
            await websocket.send_json(message)
            
            # 5. 更新最后活动时间
            self.last_activity[thread_id] = datetime.utcnow()
            
            logger.debug(f"📤 消息发送成功: {thread_id}, 类型: {message.get('type')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 消息发送失败 {thread_id}: {str(e)}")
            
            # 发送失败，从活跃连接中移除
            if thread_id in self.active_connections:
                del self.active_connections[thread_id]
            
            return False
    
    async def send_event(self, thread_id: str, event: dict):
        """发送事件（send_message的别名，语义更清晰）"""
        await self.send_message(thread_id, event)
    
    async def broadcast(self, message: dict, exclude: Optional[List[str]] = None):
        """广播消息给所有连接
        
        Args:
            message: 消息内容
            exclude: 排除的thread_id列表
        """
        exclude = exclude or []
        sent_count = 0
        
        for thread_id in list(self.active_connections.keys()):
            if thread_id in exclude:
                continue
                
            success = await self.send_message(thread_id, message)
            if success:
                sent_count += 1
        
        logger.info(f"📢 广播完成: 发送给 {sent_count} 个连接")
    
    async def get_connection_status(self, thread_id: str) -> dict:
        """获取连接状态
        
        Args:
            thread_id: 对话ID
            
        Returns:
            状态信息
        """
        is_active = thread_id in self.active_connections
        last_active = self.last_activity.get(thread_id)
        pending_count = len(self.pending_messages.get(thread_id, []))
        
        return {
            "thread_id": thread_id,
            "is_active": is_active,
            "last_active": last_active.isoformat() if last_active else None,
            "pending_messages": pending_count
        }
    
    async def get_all_connections(self) -> List[str]:
        """获取所有活跃连接ID"""
        return list(self.active_connections.keys())
    
    async def cleanup_inactive(self, max_idle_minutes: int = 30):
        """清理不活跃连接
        
        Args:
            max_idle_minutes: 最大空闲时间（分钟）
        """
        now = datetime.utcnow()
        to_remove = []
        
        for thread_id, last_active in self.last_activity.items():
            idle_time = (now - last_active).total_seconds() / 60
            if idle_time > max_idle_minutes:
                to_remove.append(thread_id)
        
        for thread_id in to_remove:
            logger.info(f"🧹 清理不活跃连接: {thread_id} (空闲{idle_time:.1f}分钟)")
            await self.disconnect(thread_id, reason="连接超时")
    
    # ==================== 私有方法 ====================
    
    async def _load_and_send_history(self, thread_id: str):
        """加载历史对话并发送给客户端
        
        Args:
            thread_id: 对话ID
        """
        try:
            # 1. 从数据库加载完整对话
            conversation = await self.store.load_full_conversation(thread_id)
            
            if conversation:
                # 2. 发送历史消息
                messages = conversation.get('messages', [])
                if messages:
                    await self.send_event(thread_id, {
                        "type": EventType.SYNC,
                        "data": {
                            "type": "history",
                            "messages": messages,
                            "count": len(messages)
                        }
                    })
                    logger.info(f"📜 发送历史消息 {len(messages)} 条: {thread_id}")
                
                # 3. 发送当前状态
                await self.send_event(thread_id, {
                    "type": EventType.SYNC,
                    "data": {
                        "type": "state",
                        "phase": conversation.get('phase', Phase.PLANNING),
                        "sections": conversation.get('sections', [])
                    }
                })
            else:
                # 新对话，不需要发送历史
                logger.info(f"🆕 新对话，无历史记录: {thread_id}")
                
        except Exception as e:
            logger.error(f"❌ 加载历史失败 {thread_id}: {str(e)}")
    
    async def _flush_pending_messages(self, thread_id: str):
        """发送缓存的未送达消息（断线重连时调用）
        
        Args:
            thread_id: 对话ID
        """
        if thread_id not in self.pending_messages:
            return
        
        pending = self.pending_messages[thread_id]
        if not pending:
            return
        
        logger.info(f"📨 发送缓存的 {len(pending)} 条消息: {thread_id}")
        
        for item in pending:
            await self.send_message(thread_id, item["message"])
        
        # 清空缓存
        self.pending_messages[thread_id] = []




# ✅ 管理WebSocket连接（connect/disconnect）

# ✅ 发送消息（send_message/broadcast）

# ✅ 集成 ConversationStore 加载历史

# ✅ 缓存消息（为断线重连做准备）

# ✅ 连接状态查询

# ✅ 清理不活跃连接