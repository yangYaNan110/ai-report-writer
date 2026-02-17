"""
WebSocket控制器 - 完整版本
架构：每个对话一个 ConversationStore + 全局 Agent + 全局 DB
特点：连接时加载历史、实时同步、内存缓存

阶段3.4
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import asyncio
import json
from loguru import logger
from datetime import datetime
import uuid

from store.conversation_store import ConversationStore
from store.database import db  # 全局单例
from agents.report_agent import ReportAgent
from models.events import EventType
from models.state import MessageRole

# 创建路由器
router = APIRouter()

# ==================== 全局 Agent 引用 ====================

# 将由 main.py 在 lifespan 中设置
_agent_instance: Optional[ReportAgent] = None

def set_agent(agent: ReportAgent):
    """设置全局 Agent 实例（在应用启动时调用）"""
    global _agent_instance
    _agent_instance = agent
    logger.info("🤖 WebSocket 控制器已获取 Agent 引用")

def get_agent() -> ReportAgent:
    """获取全局 Agent 实例"""
    if _agent_instance is None:
        raise RuntimeError("Agent 未初始化，请检查应用启动顺序")
    return _agent_instance

# ==================== 活跃对话管理 ====================

# 存储活跃的对话实例（每个对话一个 ConversationStore）
# key: thread_id, value: ConversationStore 实例
active_conversations: Dict[str, ConversationStore] = {}

async def get_or_create_conversation(thread_id: str) -> ConversationStore:
    """获取或创建对话实例
    
    每个对话独立实例，包含内存缓存
    连接时加载：使用异步工厂方法创建，自动从数据库加载历史
    """
    if thread_id not in active_conversations:
        # 使用异步工厂方法创建（会自动加载历史）
        conv = await ConversationStore.create(db, thread_id)
        active_conversations[thread_id] = conv
        logger.info(f"📁 创建/加载对话实例: {thread_id}, 历史消息数: {len(conv.messages)}")
    else:
        conv = active_conversations[thread_id]
        logger.debug(f"🔄 复用现有对话实例: {thread_id}")
    
    return conv

def remove_conversation(thread_id: str):
    """移除对话实例（连接断开时调用）"""
    if thread_id in active_conversations:
        del active_conversations[thread_id]
        logger.info(f"📁 对话实例已移除: {thread_id}, 剩余活跃对话: {len(active_conversations)}")

# ==================== WebSocket 主端点 ====================

@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """
    WebSocket 主端点
    
    Args:
        websocket: WebSocket连接
        thread_id: 对话ID（客户端生成，用于区分不同对话）
    """
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"📨 WebSocket连接请求: {thread_id} 来自 {client_host}")
    
    try:
        # 1. 获取或创建对话实例（连接时加载历史）
        conv = await get_or_create_conversation(thread_id)
        
        # 2. 接受WebSocket连接
        await websocket.accept()
        logger.info(f"✅ WebSocket连接成功: {thread_id}")
        
        # 3. 发送连接成功消息和历史状态
        await send_sync_state(websocket, thread_id, conv)
        
        # 4. 消息处理循环
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            logger.debug(f"📥 收到消息 {thread_id}: {data.get('type')}")
            
            # 处理消息
            await handle_websocket_message(websocket, thread_id, conv, data)
            
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket断开连接: {thread_id}")
        # 连接断开时移除实例（数据已实时存库，不需要额外操作）
        remove_conversation(thread_id)
        
    except Exception as e:
        logger.error(f"❌ WebSocket错误 {thread_id}: {str(e)}")
        # 发生错误时也移除实例
        remove_conversation(thread_id)
        try:
            await websocket.close(code=1011, reason=f"服务器错误: {str(e)}")
        except:
            pass

# ==================== 消息分发 ====================

async def handle_websocket_message(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict
):
    """分发处理不同类型的消息"""
    
    event_type = data.get("type")
    event_data = data.get("data", {})
    request_id = data.get("request_id")
    
    # 根据事件类型分发
    if event_type == EventType.PING:
        await handle_ping(websocket, thread_id, event_data, request_id)
        
    elif event_type == EventType.START:
        await handle_start(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.MESSAGE:
        await handle_message(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.CANCEL:
        await handle_cancel(websocket, thread_id, conv, event_data, request_id)
        
    else:
        # 未知事件类型
        logger.warning(f"⚠️ 未知事件类型: {event_type} from {thread_id}")
        await send_error(
            websocket,
            thread_id,
            code="UNKNOWN_EVENT",
            message=f"不支持的事件类型: {event_type}",
            request_id=request_id
        )

# ==================== 事件处理器 ====================

async def handle_ping(
    websocket: WebSocket,
    thread_id: str,
    data: dict,
    request_id: Optional[str] = None
):
    """处理心跳检测"""
    await websocket.send_json({
        "type": EventType.PONG,
        "data": {
            "timestamp": datetime.utcnow().isoformat(),
            "echo": data
        },
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    logger.debug(f"💓 心跳响应: {thread_id}")

async def handle_start(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """开始新对话（或重置现有对话）"""
    try:
        title = data.get("title", "新对话")
        context = data.get("context", {})
        
        # 检查是否是已有对话
        if conv.messages:
            # 已有对话，返回当前状态
            logger.info(f"🔄 对话已存在: {thread_id}")
            await websocket.send_json({
                "type": EventType.SYNC,
                "data": {
                    "type": "state",
                    "thread_id": thread_id,
                    "title": conv.conversation.get("title", title),
                    "phase": conv.get_phase(),
                    "message_count": len(conv.messages),
                    "section_count": len(conv.sections)
                },
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            # 新对话，更新标题
            await conv.update_info(title=title, context=context)
            
            # 添加系统消息
            system_msg = {
                "id": str(uuid.uuid4()),
                "role": MessageRole.SYSTEM,
                "content": "对话已开始",
                "created_at": datetime.utcnow().isoformat(),
                "metadata": {"event": "start"}
            }
            await conv.add_message(system_msg)
            
            logger.info(f"✅ 新对话创建成功: {thread_id} - {title}")
            
            await websocket.send_json({
                "type": EventType.SYNC,
                "data": {
                    "type": "start_confirmed",
                    "thread_id": thread_id,
                    "title": title
                },
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except Exception as e:
        logger.error(f"❌ 开始对话失败 {thread_id}: {str(e)}")
        await send_error(
            websocket,
            thread_id,
            code="START_FAILED",
            message=f"开始对话失败: {str(e)}",
            request_id=request_id
        )

async def handle_message(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理用户消息"""
    try:
        content = data.get("content", "").strip()
        reply_to = data.get("reply_to")
        
        if not content:
            await send_error(
                websocket,
                thread_id,
                code="EMPTY_MESSAGE",
                message="消息内容不能为空",
                request_id=request_id
            )
            return
        
        # 1. 保存用户消息（实时同步：内存+数据库）
        user_message = {
            "id": str(uuid.uuid4()),
            "role": MessageRole.USER,
            "content": content,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": {
                "reply_to": reply_to
            }
        }
        await conv.add_message(user_message)
        
        # 2. 发送消息已接收确认
        await websocket.send_json({
            "type": EventType.SYNC,
            "data": {
                "type": "message_received",
                "message_id": user_message["id"]
            },
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # 3. 获取 Agent 并生成回复（流式）
        agent = get_agent()
        
        # 准备消息历史（从内存缓存获取）
        messages_for_agent = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in conv.get_recent_messages(10)  # 最近10条，避免token超限
        ]
        
        # 4. 流式生成回复
        full_response = ""
        message_id = str(uuid.uuid4())
        
        async for chunk in agent.run(messages_for_agent, stream=True):
            if chunk.get("type") == "chunk":
                text = chunk.get("content", "")
                full_response += text
                
                # 发送流式片段
                await websocket.send_json({
                    "type": EventType.CHUNK,
                    "data": {
                        "text": text,
                        "done": False,
                        "message_id": message_id
                    },
                    "request_id": request_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            elif chunk.get("type") == "complete":
                # 生成完成，保存 AI 回复（实时同步）
                assistant_message = {
                    "id": message_id,
                    "role": MessageRole.ASSISTANT,
                    "content": full_response,
                    "created_at": datetime.utcnow().isoformat(),
                    "metadata": {
                        "model": chunk.get("model", "unknown"),
                        "tokens": chunk.get("tokens", 0)
                    }
                }
                await conv.add_message(assistant_message)
                
                # 发送完成事件
                await websocket.send_json({
                    "type": EventType.COMPLETE,
                    "data": {
                        "message_id": message_id,
                        "full_content": full_response,
                        "metadata": assistant_message["metadata"]
                    },
                    "request_id": request_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                logger.info(f"✅ Agent回复完成 {thread_id}: {len(full_response)}字符")
        
    except Exception as e:
        logger.error(f"❌ 处理消息失败 {thread_id}: {str(e)}")
        await send_error(
            websocket,
            thread_id,
            code="MESSAGE_HANDLING_FAILED",
            message=f"处理消息失败: {str(e)}",
            request_id=request_id
        )

async def handle_cancel(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """取消当前操作"""
    # TODO: 阶段5实现真正的取消逻辑
    await websocket.send_json({
        "type": EventType.SYNC,
        "data": {
            "type": "cancel_not_implemented",
            "message": "取消功能正在开发中"
        },
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    })

# ==================== 辅助函数 ====================

async def send_sync_state(websocket: WebSocket, thread_id: str, conv: ConversationStore):
    """发送同步状态（连接时调用）"""
    
    # 1. 发送连接成功
    await websocket.send_json({
        "type": EventType.SYNC,
        "data": {
            "type": "connected",
            "thread_id": thread_id,
            "message": "连接成功"
        },
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # 2. 如果有历史消息，发送历史
    if conv.messages:
        # 发送最近10条消息作为历史
        recent_messages = conv.get_recent_messages(10)
        await websocket.send_json({
            "type": EventType.SYNC,
            "data": {
                "type": "history",
                "messages": recent_messages,
                "total": len(conv.messages),
                "shown": len(recent_messages)
            },
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # 3. 发送当前状态
    await websocket.send_json({
        "type": EventType.SYNC,
        "data": {
            "type": "state",
            "thread_id": thread_id,
            "phase": conv.get_phase(),
            "title": conv.conversation.get("title", "新对话"),
            "sections": conv.get_sections()
        },
        "timestamp": datetime.utcnow().isoformat()
    })

async def send_error(
    websocket: WebSocket,
    thread_id: str,
    code: str,
    message: str,
    details: dict = None,
    request_id: Optional[str] = None
):
    """发送错误消息"""
    await websocket.send_json({
        "type": EventType.ERROR,
        "data": {
            "code": code,
            "message": message,
            "details": details or {}
        },
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat()
    })

# ==================== 状态查询接口 ====================

@router.get("/ws/status")
async def websocket_status():
    """获取WebSocket连接状态（用于监控）"""
    return {
        "active_conversations": len(active_conversations),
        "threads": list(active_conversations.keys()),
        "agent_ready": _agent_instance is not None
    }

@router.get("/ws/conversation/{thread_id}")
async def get_conversation_info(thread_id: str):
    """获取指定对话的信息（不通过WebSocket）"""
    if thread_id in active_conversations:
        conv = active_conversations[thread_id]
        return {
            "thread_id": thread_id,
            "active": True,
            "message_count": len(conv.messages),
            "section_count": len(conv.sections),
            "phase": conv.get_phase(),
            "title": conv.conversation.get("title")
        }
    else:
        # 从数据库查询
        info = await db.get_conversation(thread_id)
        if info:
            return {
                "thread_id": thread_id,
                "active": False,
                **info
            }
        else:
            return {"thread_id": thread_id, "active": False, "exists": False}