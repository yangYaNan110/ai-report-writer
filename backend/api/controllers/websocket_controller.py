"""
WebSocket控制器 - 完整版本
使用 EventType 模型进行事件分发
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import asyncio
import json
from loguru import logger
from datetime import datetime
import uuid

from store.conversation_store import ConversationStore
from store.database import db
from agents.report_agent import ReportAgent
from models.events import (
    EventType, ClientEvent, ServerEvent,
    StartEventData, MessageEventData, ApproveEventData,
    EditSectionEventData, RegenerateEventData, PingEventData,
    ChunkEventData, CompleteEventData, SyncEventData,
    SectionReadyEventData, PromptEventData, InterruptEventData,
    TaskProgressEventData, SectionUpdatedEventData,
    ReportCompletedEventData, ErrorEventData, PongEventData
)

router = APIRouter()

# ==================== 全局 Agent 引用 ====================

_agent_instance: Optional[ReportAgent] = None

def set_agent(agent: ReportAgent):
    global _agent_instance
    _agent_instance = agent
    logger.info("🤖 WebSocket 控制器已获取 Agent 引用")

def get_agent() -> ReportAgent:
    if _agent_instance is None:
        raise RuntimeError("Agent 未初始化")
    return _agent_instance

# ==================== 活跃对话管理 ====================

active_conversations: Dict[str, ConversationStore] = {}

async def get_or_create_conversation(thread_id: str) -> ConversationStore:
    if thread_id not in active_conversations:
        conv = await ConversationStore.create(db, thread_id)
        active_conversations[thread_id] = conv
        logger.info(f"📁 创建/加载对话实例: {thread_id}, 历史消息数: {len(conv.messages)}")
    else:
        conv = active_conversations[thread_id]
    
    return conv

def remove_conversation(thread_id: str):
    if thread_id in active_conversations:
        del active_conversations[thread_id]
        logger.info(f"📁 对话实例已移除: {thread_id}")

# ==================== WebSocket 主端点 ====================

@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"📨 WebSocket连接请求: {thread_id} 来自 {client_host}")
    
    try:
        conv = await get_or_create_conversation(thread_id)
        await websocket.accept()
        logger.info(f"✅ WebSocket连接成功: {thread_id}")
        
        # 发送同步状态
        await send_sync_state(websocket, thread_id, conv)
        
        while True:
            data = await websocket.receive_json()
            logger.debug(f"📥 收到消息 {thread_id}: {data.get('type')}")
            
            # 使用 EventType 进行分发
            await handle_websocket_message(websocket, thread_id, conv, data)
            
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket断开连接: {thread_id}")
        remove_conversation(thread_id)
    except Exception as e:
        logger.error(f"❌ WebSocket错误 {thread_id}: {str(e)}")
        remove_conversation(thread_id)
        try:
            await websocket.close(code=1011, reason=f"服务器错误: {str(e)}")
        except:
            pass

# ==================== 消息分发（使用 EventType）====================

async def handle_websocket_message(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict
):
    """使用 EventType 分发消息"""
    
    event_type = data.get("type")
    event_data = data.get("data", {})
    request_id = data.get("request_id")
    
    # 根据 EventType 分发
    if event_type == EventType.PING:
        await handle_ping(websocket, thread_id, event_data, request_id)
        
    elif event_type == EventType.START:
        await handle_start(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.MESSAGE:
        await handle_message(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type in [EventType.APPROVE, EventType.APPROVE_SECTION]:
        # 兼容两种确认事件
        await handle_approve(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.EDIT_SECTION:
        await handle_edit_section(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.REGENERATE:
        await handle_regenerate(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.CANCEL:
        await handle_cancel(websocket, thread_id, conv, event_data, request_id)
        
    else:
        logger.warning(f"⚠️ 未知事件类型: {event_type}")
        await send_error(
            websocket,
            thread_id,
            code="UNKNOWN_EVENT",
            message=f"不支持的事件类型: {event_type}",
            request_id=request_id
        )

# ==================== 事件处理器（使用 EventType 发送）====================

async def handle_ping(
    websocket: WebSocket,
    thread_id: str,
    data: dict,
    request_id: Optional[str] = None
):
    """处理心跳"""
    pong_data = PongEventData(
        timestamp=datetime.utcnow().isoformat(),
        echo=data
    )
    
    await websocket.send_json(ServerEvent(
        type=EventType.PONG,
        data=pong_data.__dict__,
        request_id=request_id
    ).__dict__)
    
    logger.debug(f"💓 心跳响应: {thread_id}")


async def handle_start(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """开始新对话"""
    try:
        start_data = StartEventData(
            title=data.get("title"),
            context=data.get("context")
        )
        
        if conv.messages:
            # 已有对话，返回当前状态
            await websocket.send_json(ServerEvent(
                type=EventType.SYNC,
                data=SyncEventData(
                    type="state",
                    thread_id=thread_id,
                    phase=conv.get_phase(),
                    title=conv.state.get("title", start_data.title),
                    message_count=len(conv.messages),
                    section_count=len(conv.sections)
                ).__dict__,
                request_id=request_id
            ).__dict__)
        else:
            # 新对话，生成报告
            await conv.generate_report(start_data.title or "新对话")
            
            # 发送大纲确认提示
            await websocket.send_json(ServerEvent(
                type=EventType.PROMPT,
                data=PromptEventData(
                    question="大纲已生成，您满意吗？",
                    options=["确认", "修改大纲"],
                    context={"sections": conv.sections}
                ).__dict__,
                request_id=request_id
            ).__dict__)
            
    except Exception as e:
        logger.error(f"❌ 开始对话失败: {e}")
        await send_error(websocket, thread_id, "START_FAILED", str(e), request_id=request_id)


async def handle_message(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理用户消息"""
    try:
        msg_data = MessageEventData(
            content=data.get("content", "").strip(),
            reply_to=data.get("reply_to")
        )
        
        if not msg_data.content:
            await send_error(
                websocket, thread_id,
                "EMPTY_MESSAGE", "消息内容不能为空",
                request_id=request_id
            )
            return
        
        # 保存用户消息
        from models.state import MessageRole
        user_message = {
            "id": str(uuid.uuid4()),
            "role": MessageRole.USER,
            "content": msg_data.content,
            "created_at": datetime.now().isoformat(),
            "metadata": {"reply_to": msg_data.reply_to}
        }
        await conv.add_message(user_message)
        
        # 发送已接收确认
        await websocket.send_json(ServerEvent(
            type=EventType.SYNC,
            data=SyncEventData(
                type="message_received",
                message_id=user_message["id"]
            ).__dict__,
            request_id=request_id
        ).__dict__)
        
        # 获取Agent回复
        agent = get_agent()
        messages_for_agent = [
            {"role": m["role"], "content": m["content"]}
            for m in conv.get_recent_messages(10)
        ]
        
        # 流式回复
        full_response = ""
        message_id = str(uuid.uuid4())
        
        async for chunk in agent.run(messages_for_agent, stream=True):
            if chunk.get("type") == "chunk":
                text = chunk.get("content", "")
                full_response += text
                
                await websocket.send_json(ServerEvent(
                    type=EventType.CHUNK,
                    data=ChunkEventData(
                        text=text,
                        done=False,
                        message_id=message_id
                    ).__dict__,
                    request_id=request_id
                ).__dict__)
                
            elif chunk.get("type") == "complete":
                # 保存AI回复
                assistant_message = {
                    "id": message_id,
                    "role": MessageRole.ASSISTANT,
                    "content": full_response,
                    "created_at": datetime.utcnow().isoformat(),
                    "metadata": chunk.get("metadata", {})
                }
                await conv.add_message(assistant_message)
                
                await websocket.send_json(ServerEvent(
                    type=EventType.COMPLETE,
                    data=CompleteEventData(
                        message_id=message_id,
                        full_content=full_response,
                        metadata=assistant_message["metadata"]
                    ).__dict__,
                    request_id=request_id
                ).__dict__)
                
    except Exception as e:
        logger.error(f"❌ 处理消息失败: {e}")
        await send_error(websocket, thread_id, "MESSAGE_ERROR", str(e), request_id=request_id)


async def handle_approve(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理确认（大纲或段落）"""
    try:
        approve_data = ApproveEventData(
            section_id=data.get("section_id"),
            feedback=data.get("feedback")
        )
        
        if approve_data.section_id:
            # 确认段落
            await conv.approve_section(approve_data.section_id)
            
            # 检查是否所有段落都完成了
            if conv.state.phase == "completed":
                await websocket.send_json(ServerEvent(
                    type=EventType.REPORT_COMPLETED,
                    data=ReportCompletedEventData(
                        total_sections=len(conv.sections),
                        total_words=sum(len(s.content) for s in conv.sections)
                    ).__dict__,
                    request_id=request_id
                ).__dict__)
            else:
                # 继续下一段
                await websocket.send_json(ServerEvent(
                    type=EventType.STATE_CHANGE,
                    data={"phase": conv.state.phase, "current_section": conv.state.current_section_id},
                    request_id=request_id
                ).__dict__)
        else:
            # 确认大纲
            await conv.approve_plan()
            
    except Exception as e:
        await send_error(websocket, thread_id, "APPROVE_ERROR", str(e), request_id=request_id)


async def handle_edit_section(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理修改段落"""
    try:
        edit_data = EditSectionEventData(
            section_id=data.get("section_id"),
            instruction=data.get("instruction", "")
        )
        
        if not edit_data.section_id:
            await send_error(websocket, thread_id, "INVALID_REQUEST", "缺少section_id", request_id=request_id)
            return
        
        # 执行修改
        new_content = await conv.edit_section(edit_data.section_id, edit_data.instruction)
        section = conv._get_section(edit_data.section_id)
        
        # 发送更新后的段落
        await websocket.send_json(ServerEvent(
            type=EventType.SECTION_UPDATED,
            data=SectionUpdatedEventData(
                section_id=edit_data.section_id,
                content=new_content,
                version=section.version,
                status=section.status
            ).__dict__,
            request_id=request_id
        ).__dict__)
        
        # 询问是否满意
        await websocket.send_json(ServerEvent(
            type=EventType.PROMPT,
            data=PromptEventData(
                question=f"{section.title}修改完成，您满意吗？",
                options=["确认", "再次修改"]
            ).__dict__,
            request_id=request_id
        ).__dict__)
        
    except Exception as e:
        await send_error(websocket, thread_id, "EDIT_ERROR", str(e), request_id=request_id)


async def handle_regenerate(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理重写段落"""
    try:
        regen_data = RegenerateEventData(
            section_id=data.get("section_id")
        )
        
        if not regen_data.section_id:
            await send_error(websocket, thread_id, "INVALID_REQUEST", "缺少section_id", request_id=request_id)
            return
        
        # 流式重写
        async for chunk in conv.regenerate_section(regen_data.section_id):
            await websocket.send_json(ServerEvent(
                type=EventType.CHUNK,
                data=ChunkEventData(
                    text=chunk.get("content", ""),
                    section_id=regen_data.section_id,
                    done=chunk.get("done", False)
                ).__dict__,
                request_id=request_id
            ).__dict__)
        
        # 完成后询问
        section = conv._get_section(regen_data.section_id)
        await websocket.send_json(ServerEvent(
            type=EventType.PROMPT,
            data=PromptEventData(
                question=f"{section.title}重写完成，您满意吗？",
                options=["确认", "再次修改"]
            ).__dict__,
            request_id=request_id
        ).__dict__)
        
    except Exception as e:
        await send_error(websocket, thread_id, "REGENERATE_ERROR", str(e), request_id=request_id)


async def handle_cancel(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理取消"""
    # TODO: 阶段5实现真正的取消逻辑
    await websocket.send_json(ServerEvent(
        type=EventType.SYNC,
        data=SyncEventData(
            type="cancel_not_implemented",
            message="取消功能正在开发中"
        ).__dict__,
        request_id=request_id
    ).__dict__)


# ==================== 辅助函数 ====================

async def send_sync_state(websocket: WebSocket, thread_id: str, conv: ConversationStore):
    """发送同步状态"""
    
    # 1. 连接成功
    await websocket.send_json(ServerEvent(
        type=EventType.SYNC,
        data=SyncEventData(
            type="connected",
            thread_id=thread_id,
            message="连接成功"
        ).__dict__
    ).__dict__)
    
    # 2. 历史消息
    if conv.messages:
        recent = conv.get_recent_messages(10)
        await websocket.send_json(ServerEvent(
            type=EventType.SYNC,
            data=SyncEventData(
                type="history",
                messages=recent,
                total=len(conv.messages),
                shown=len(recent)
            ).__dict__
        ).__dict__)
    
    # 3. 当前状态
    await websocket.send_json(ServerEvent(
        type=EventType.SYNC,
        data=SyncEventData(
            type="state",
            thread_id=thread_id,
            phase=conv.get_phase(),
            title=conv.state.get("title", "新对话"),
            sections=conv.sections,
            pending_question=conv.state.get("pending_question"),
            pending_options=conv.state.get("pending_options")
        ).__dict__
    ).__dict__)


async def send_error(
    websocket: WebSocket,
    thread_id: str,
    code: str,
    message: str,
    details: dict = None,
    request_id: Optional[str] = None
):
    """发送错误"""
    await websocket.send_json(ServerEvent(
        type=EventType.ERROR,
        data=ErrorEventData(
            code=code,
            message=message,
            details=details
        ).__dict__,
        request_id=request_id
    ).__dict__)


# ==================== 状态查询接口 ====================

@router.get("/ws/status")
async def websocket_status():
    return {
        "active_conversations": len(active_conversations),
        "threads": list(active_conversations.keys()),
        "agent_ready": _agent_instance is not None
    }


@router.get("/ws/conversation/{thread_id}")
async def get_conversation_info(thread_id: str):
    if thread_id in active_conversations:
        conv = active_conversations[thread_id]
        return {
            "thread_id": thread_id,
            "active": True,
            "message_count": len(conv.messages),
            "section_count": len(conv.sections),
            "phase": conv.get_phase(),
            "title": conv.state.get("title")
        }
    else:
        info = await db.get_conversation(thread_id)
        if info:
            return {"thread_id": thread_id, "active": False, **info}
        else:
            return {"thread_id": thread_id, "active": False, "exists": False}