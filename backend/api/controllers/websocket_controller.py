"""
WebSocket控制器 - 完整版本
使用纯数据模型处理事件
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional
from loguru import logger
from store.conversation_store import ConversationStore

from agents.report_agent import ReportAgent
import asyncio
router = APIRouter()

# ==================== 全局 Agent 引用 ====================

_agent_instance: Optional[ReportAgent] = None

def set_agent(agent: ReportAgent):
    """设置全局 Agent 实例"""
    print(f"设置全局 Agent 实例: {agent}")
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

async def get_or_create_conversation(thread_id: str, websocket: WebSocket = None) -> ConversationStore:
    """获取或创建对话实例"""
    if thread_id not in active_conversations:
        conv = await ConversationStore.create(thread_id, websocket, get_agent())
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
    current_task = None  # 跟踪当前任务
    try:
        conv = await get_or_create_conversation(thread_id, websocket)
        await websocket.accept()
        logger.info(f"✅ WebSocket连接成功: {thread_id}")
        while True:
            data = await websocket.receive_json()
            data = data.get("data", "").get("content","")
            
            # 取消旧任务
            if current_task and not current_task.done():
                current_task.cancel()
                try:
                    # 给旧任务一点时间清理
                    await asyncio.wait_for(current_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
             # 创建新任务
            current_task = asyncio.create_task(
                handle_websocket_message(conv, data)
            )
            
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
    finally:
        # 清理最后一个任务
        if current_task and not current_task.done():
            current_task.cancel()

# ==================== 消息分发 ====================

async def handle_websocket_message(
    conv: ConversationStore,
    data: Dict
):
    """处理消息"""
    try:
        # 处理消息
        await conv.process_message(data)
    except asyncio.CancelledError:
        # 任务被取消时的清理工作
        logger.info("handle_websocket_message 被取消")
        # 可以在这里做清理，比如通知前端
        try:
            await conv.websocket.send_json({
                "type": "cancelled",
                "message": "您的请求被新指令取代"
            })
        except:
            pass
        raise  # 重新抛出，让上层知道被取消了
    except Exception as e:
        logger.error(f"处理消息错误: {e}")


    
   



# ==================== 状态查询接口 ====================

@router.get("/ws/status")
async def websocket_status():
    """获取WebSocket连接状态"""
    return {
        "active_conversations": len(active_conversations),
        "threads": list(active_conversations.keys()),
        "agent_ready": _agent_instance is not None
    }


