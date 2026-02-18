"""
WebSocket控制器 - 完整版本
使用纯数据模型处理事件
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import asyncio
from loguru import logger
from datetime import datetime, timezone
import uuid

from store.conversation_store import ConversationStore
from store.database import db
from agents.report_agent import ReportAgent
from models.state import MessageRole, Phase
from models.events import (
    EventType, ServerEvent,
    StartEventData, MessageEventData, ApproveEventData,
    EditSectionEventData, RegenerateEventData, PingEventData,
    ChunkEventData, CompleteEventData, SyncEventData,
    PromptEventData, InterruptEventData, TaskProgressEventData,
    SectionUpdatedEventData, ReportCompletedEventData,
    ErrorEventData, PongEventData
)

router = APIRouter()

# ==================== 全局 Agent 引用 ====================

_agent_instance: Optional[ReportAgent] = None

def set_agent(agent: ReportAgent):
    """设置全局 Agent 实例"""
    global _agent_instance
    _agent_instance = agent
    logger.info("🤖 WebSocket 控制器已获取 Agent 引用")

def get_agent() -> ReportAgent:
    """获取全局 Agent 实例"""
    if _agent_instance is None:
        raise RuntimeError("Agent 未初始化")
    return _agent_instance

# ==================== 活跃对话管理 ====================

active_conversations: Dict[str, ConversationStore] = {}

async def get_or_create_conversation(thread_id: str) -> ConversationStore:
    """获取或创建对话实例"""
    if thread_id not in active_conversations:
        conv = await ConversationStore.create(db, thread_id)
        active_conversations[thread_id] = conv
        logger.info(f"📁 创建/加载对话实例: {thread_id}")
    else:
        conv = active_conversations[thread_id]
    
    return conv

def remove_conversation(thread_id: str):
    """移除对话实例"""
    if thread_id in active_conversations:
        del active_conversations[thread_id]
        logger.info(f"📁 对话实例已移除: {thread_id}")

# ==================== WebSocket 主端点 ====================

@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """WebSocket 主端点"""
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

# ==================== 消息分发 ====================

async def handle_websocket_message(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict
):
    """分发处理消息"""
    event_type = data.get("type")
    event_data = data.get("data", {})
    request_id = data.get("request_id")
    
    if event_type == EventType.PING:
        await handle_ping(websocket, thread_id, event_data, request_id)
        
    elif event_type == EventType.START:
        await handle_start(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type == EventType.MESSAGE:
        await handle_message(websocket, thread_id, conv, event_data, request_id)
        
    elif event_type in [EventType.APPROVE, EventType.APPROVE_SECTION]:
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
            websocket, thread_id,
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
    """处理心跳"""
    pong_data = PongEventData(
        timestamp=datetime.now(timezone.utc).isoformat(),
        echo=data
    )
    
    await websocket.send_json(ServerEvent(
        type=EventType.PONG,
        data=pong_data.to_dict(),
        request_id=request_id,
        timestamp=datetime.now(timezone.utc)
    ).to_dict())
    
    logger.debug(f"💓 心跳响应: {thread_id}")


async def handle_start(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """开始新对话"""
    
    print("handle_start data:", data)  # 调试输出，查看前端发送的数据结构
    print("-" * 50)
    try:
        start_data = StartEventData.from_dict(data)
        
        if conv.messages:
            print("已有对话，返回当前状态")  # 调试输出
            # 已有对话，返回当前状态
            await websocket.send_json(ServerEvent(
                type=EventType.SYNC,
                data=SyncEventData(
                    type="state",
                    thread_id=thread_id,
                    phase=conv.get_phase(),
                    title=conv.conversation.title,
                    extra={
                        "message_count": len(conv.messages),
                        "section_count": len(conv.sections)
                    }
                ).to_dict(),
                request_id=request_id,
                timestamp=datetime.now(timezone.utc)
            ).to_dict())
        else:
            # 新对话，生成报告（使用流式模式）
            async for chunk in conv.generate_report_stream(
                topic=start_data.title or "新对话",
            ):
                print("handle_start chunk:", chunk)  # 调试输出，查看流式返回的数据结构
                if chunk["type"] == "outline_complete":
                    # 大纲完成，发送确认提示
                    await websocket.send_json(ServerEvent(
                        type=EventType.PROMPT,
                        data=PromptEventData(
                            question=chunk["pending_question"],
                            options=chunk["pending_options"]
                        ).to_dict(),
                        request_id=request_id
                    ).to_dict())
                elif chunk["type"] == "error":
                    await send_error(websocket, thread_id, "GENERATE_ERROR", chunk["message"], request_id=request_id)
                else:
                    # 流式内容
                    await websocket.send_json(ServerEvent(
                        type=EventType.CHUNK,
                        data=chunk,
                        request_id=request_id
                    ).to_dict())
            
    except Exception as e:
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
        msg_data = MessageEventData.from_dict(data)
        
        if not msg_data.content:
            await send_error(
                websocket, thread_id,
                "EMPTY_MESSAGE", "消息内容不能为空",
                request_id=request_id
            )
            return
        
        # 保存用户消息
        user_msg = await conv.add_message(
            role=MessageRole.USER,
            content=msg_data.content,
            metadata={"reply_to": msg_data.reply_to}
        )
        
        # 发送已接收确认
        await websocket.send_json(ServerEvent(
            type=EventType.SYNC,
            data={"type": "message_received", "message_id": user_msg.id},
            request_id=request_id,
            timestamp=datetime.now(timezone.utc)
        ).to_dict())
        
        # 获取Agent回复
        agent = get_agent()
        messages_for_agent = conv.get_recent_messages(10)
        
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
                    ).to_dict(),
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc)
                ).to_dict())
                
            elif chunk.get("type") == "complete":
                # 保存AI回复
                assistant_msg = await conv.add_message(
                    role=MessageRole.ASSISTANT,
                    content=full_response,
                    metadata=chunk.get("metadata", {})
                )
                
                await websocket.send_json(ServerEvent(
                    type=EventType.COMPLETE,
                    data=CompleteEventData(
                        message_id=assistant_msg.id,
                        full_content=full_response,
                        metadata=chunk.get("metadata", {})
                    ).to_dict(),
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc)
                ).to_dict())
                
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
    """处理确认"""
    try:
        approve_data = ApproveEventData.from_dict(data)
        
        if approve_data.section_id:
            # 确认段落
            await conv.approve_section(approve_data.section_id)
            
            # 检查是否完成
            if conv.conversation.phase == Phase.COMPLETED:
                await websocket.send_json(ServerEvent(
                    type=EventType.REPORT_COMPLETED,
                    data=ReportCompletedEventData(
                        total_sections=len(conv.sections),
                        total_words=sum(len(s.content) for s in conv.sections)
                    ).to_dict(),
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc)
                ).to_dict())
            else:
                # 继续下一段
                await websocket.send_json(ServerEvent(
                    type=EventType.STATE_CHANGE,
                    data={"phase": conv.conversation.phase.value, 
                          "current_section": conv.conversation.current_section_id},
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc)
                ).to_dict())
        else:
            # 确认大纲
            await conv.approve_plan()
            
            # 开始写作
            if conv.conversation.pending_question:
                await websocket.send_json(ServerEvent(
                    type=EventType.PROMPT,
                    data=PromptEventData(
                        question=conv.conversation.pending_question,
                        options=conv.conversation.pending_options
                    ).to_dict(),
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc)
                ).to_dict())
            
    except Exception as e:
        logger.error(f"❌ 确认失败: {e}")
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
        edit_data = EditSectionEventData.from_dict(data)
        
        if not edit_data.section_id:
            await send_error(
                websocket, thread_id,
                "INVALID_REQUEST", "缺少section_id",
                request_id=request_id
            )
            return
        
        # 执行修改
        new_content = await conv.edit_section(edit_data.section_id, edit_data.instruction)
        section = conv.get_section(edit_data.section_id)
        
        if section:
            # 发送更新后的段落
            await websocket.send_json(ServerEvent(
                type=EventType.SECTION_UPDATED,
                data=SectionUpdatedEventData(
                    section_id=edit_data.section_id,
                    content=new_content,
                    version=section.version,
                    status=section.status.value
                ).to_dict(),
                request_id=request_id,
                timestamp=datetime.now(timezone.utc)
            ).to_dict())
            
            # 询问是否满意
            if conv.conversation.pending_question:
                await websocket.send_json(ServerEvent(
                    type=EventType.PROMPT,
                    data=PromptEventData(
                        question=conv.conversation.pending_question,
                        options=conv.conversation.pending_options
                    ).to_dict(),
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc)
                ).to_dict())
        
    except Exception as e:
        logger.error(f"❌ 修改失败: {e}")
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
        regen_data = RegenerateEventData.from_dict(data)
        
        if not regen_data.section_id:
            await send_error(
                websocket, thread_id,
                "INVALID_REQUEST", "缺少section_id",
                request_id=request_id
            )
            return
        
        # 重写段落
        section = conv.get_section(regen_data.section_id)
        if section:
            # 清空内容
            section.content = ""
            section.status = SectionStatus.DRAFT
            section.version += 1
            await conv._save()
            
            # 模拟重新生成（实际应该调Agent）
            new_content = f"这是重新生成的{section.title}内容..."
            section.content = new_content
            section.status = SectionStatus.PENDING
            await conv._save()
            
            # 发送新内容
            await websocket.send_json(ServerEvent(
                type=EventType.SECTION_UPDATED,
                data=SectionUpdatedEventData(
                    section_id=regen_data.section_id,
                    content=new_content,
                    version=section.version,
                    status=section.status.value
                ).to_dict(),
                request_id=request_id,
                timestamp=datetime.now(timezone.utc)
            ).to_dict())
            
            # 询问是否满意
            conv.conversation.pending_question = f"{section.title}重写完成，您满意吗？"
            conv.conversation.pending_options = ["确认", "再次修改"]
            await conv._save()
            
            await websocket.send_json(ServerEvent(
                type=EventType.PROMPT,
                data=PromptEventData(
                    question=conv.conversation.pending_question,
                    options=conv.conversation.pending_options
                ).to_dict(),
                request_id=request_id,
                timestamp=datetime.now(timezone.utc)
            ).to_dict())
        
    except Exception as e:
        logger.error(f"❌ 重写失败: {e}")
        await send_error(websocket, thread_id, "REGENERATE_ERROR", str(e), request_id=request_id)


async def handle_cancel(
    websocket: WebSocket,
    thread_id: str,
    conv: ConversationStore,
    data: dict,
    request_id: Optional[str] = None
):
    """处理取消"""
    # 重置待处理问题
    conv.conversation.pending_question = None
    conv.conversation.pending_options = []
    await conv._save()
    
    await websocket.send_json(ServerEvent(
        type=EventType.SYNC,
        data={"type": "cancelled", "message": "操作已取消"},
        request_id=request_id,
        timestamp=datetime.now(timezone.utc)
    ).to_dict())


# ==================== 辅助函数 ====================

async def send_sync_state(websocket: WebSocket, thread_id: str, conv: ConversationStore):
    """发送同步状态"""
    
    # 1. 连接成功
    await websocket.send_json(ServerEvent(
        type=EventType.SYNC,
        data=SyncEventData(
            type="connected",
            thread_id=thread_id
        ).to_dict(),
        timestamp=datetime.now(timezone.utc)
    ).to_dict())
    
    # 2. 发送所有历史消息（不仅仅是最近10条）
    if conv.messages:
        # 将所有消息转换为前端需要的格式
        all_messages = []
        for msg in conv.messages:
            all_messages.append({
                "id": msg.id,
                "role": msg.role.value,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "section_id": msg.section_id
            })
        
        await websocket.send_json(ServerEvent(
            type=EventType.SYNC,
            data=SyncEventData(
                type="history",
                messages=all_messages,  # 发送全部消息
                total=len(conv.messages),
                shown=len(all_messages)
            ).to_dict(),
            timestamp=datetime.now(timezone.utc)
        ).to_dict())
        
        logger.info(f"📜 发送历史消息 {len(all_messages)} 条给 {thread_id}")
    
    # 3. 当前状态
    await websocket.send_json(ServerEvent(
        type=EventType.SYNC,
        data=SyncEventData(
            type="state",
            thread_id=thread_id,
            phase=conv.get_phase(),
            title=conv.conversation.title,
            sections=[s.to_dict() for s in conv.sections],
            pending_question=conv.conversation.pending_question,
            pending_options=conv.conversation.pending_options
        ).to_dict(),
        timestamp=datetime.now(timezone.utc)
    ).to_dict())


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
            details=details or {}
        ).to_dict(),
        request_id=request_id,
        timestamp=datetime.now(timezone.utc)
    ).to_dict())


# ==================== 状态查询接口 ====================

@router.get("/ws/status")
async def websocket_status():
    """获取WebSocket连接状态"""
    return {
        "active_conversations": len(active_conversations),
        "threads": list(active_conversations.keys()),
        "agent_ready": _agent_instance is not None
    }


@router.get("/ws/conversation/{thread_id}")
async def get_conversation_info(thread_id: str):
    """获取指定对话的信息"""
    if thread_id in active_conversations:
        conv = active_conversations[thread_id]
        return {
            "thread_id": thread_id,
            "active": True,
            "message_count": len(conv.messages),
            "section_count": len(conv.sections),
            "phase": conv.get_phase(),
            "title": conv.conversation.title
        }
    else:
        info = await db.get_conversation(thread_id)
        if info:
            return {"thread_id": thread_id, "active": False, **info}
        else:
            return {"thread_id": thread_id, "active": False, "exists": False}