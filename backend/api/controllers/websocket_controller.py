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
    
    try:
        conv = await get_or_create_conversation(thread_id, websocket)
        await websocket.accept()
        logger.info(f"✅ WebSocket连接成功: {thread_id}")
        while True:
            data = await websocket.receive_json()
            data = data.get("data", "")
            asyncio.create_task(
                handle_websocket_message(conv,data)
            )
            # await handle_websocket_message(conv, data)
            
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
    conv: ConversationStore,
    data: Dict
):
    """处理消息"""
    try:
        user_input = data.get("content", "")
        print(data,"006...",user_input)

        interrupt = data.get("interrupt", False)
        # 第一步：无论什么消息 先中断当前正在执行的任务
        await conv.interrupt_current_task()
        print("007....")
        # 第二步： 检查是否是纯打断指令 (后期可以交给ai来识别意图 开发阶段先实现功能)
        stop_words = ["停止", "中断", "停下"]
        if any(word in user_input for word in stop_words):
            interrupt = True
        if interrupt :
            await conv.interupt_process()
            return
        # 有实际内容的消息 交给convStore处理
        # processing内部会创建新的生成任务并保存引用
        await conv.processing(user_input=user_input)
        pass
    except asyncio.CancelledError:
        # 这个任务自己被更新消息的任务取消了
        logger.info("消息处理器被取消")
        await conv.websocket.send_json({
            "type": "cancelled",
            "message": "被新消息中断"
        })
    except Exception as e:
        logger.error(f"消息处理器错误:{e}")
        await conv.websocket.send_json({
            "type": "error",
            "message": str(e)
        })


    
   



# ==================== 状态查询接口 ====================

@router.get("/ws/status")
async def websocket_status():
    """获取WebSocket连接状态"""
    return {
        "active_conversations": len(active_conversations),
        "threads": list(active_conversations.keys()),
        "agent_ready": _agent_instance is not None
    }


