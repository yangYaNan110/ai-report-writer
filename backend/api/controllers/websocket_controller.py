"""
WebSocket控制器 - 基础版本
阶段1.2：实现基础流式输出
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
import asyncio
import json
from loguru import logger

from graph.agents.report_agent import ReportAgent

# 创建路由器
router = APIRouter()

# 存储活跃的WebSocket连接
active_connections: Dict[str, WebSocket] = {}

# Agent实例缓存
agent_instance = None

def get_agent():
    """获取或创建Agent实例"""
    global agent_instance
    if agent_instance is None:
        agent_instance = ReportAgent()
    return agent_instance

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket连接端点
    
    Args:
        websocket: WebSocket连接
        client_id: 客户端ID（可以是任意字符串，用于区分不同连接）
    """
    await websocket.accept()
    active_connections[client_id] = websocket
    logger.info(f"✅ 客户端 {client_id} 已连接")
    
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "连接成功，可以开始对话了",
                "client_id": client_id
            }
        })
        
        # 处理消息
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            logger.debug(f"收到消息 from {client_id}: {data[:50]}...")
            
            try:
                # 解析JSON
                message_data = json.loads(data)
                
                # 处理不同类型的消息
                if message_data.get("action") == "chat":
                    # 聊天消息
                    await handle_chat(websocket, client_id, message_data)
                else:
                    # 未知action
                    await websocket.send_json({
                        "type": "error",
                        "data": {
                            "message": f"未知的action: {message_data.get('action')}"
                        }
                    })
                    
            except json.JSONDecodeError:
                # 如果不是JSON，当作纯文本消息处理
                await handle_chat(websocket, client_id, {"message": data})
                
    except WebSocketDisconnect:
        # 客户端断开连接
        if client_id in active_connections:
            del active_connections[client_id]
        logger.info(f"❌ 客户端 {client_id} 已断开")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        if client_id in active_connections:
            del active_connections[client_id]

async def handle_chat(websocket: WebSocket, client_id: str, data: dict):
    """
    处理聊天消息
    
    Args:
        websocket: WebSocket连接
        client_id: 客户端ID
        data: 消息数据，包含message字段
    """
    # 获取用户消息
    user_message = data.get("message", "")
    if not user_message:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "消息不能为空"}
        })
        return
    
    # 获取Agent
    agent = get_agent()
    
    try:
        # 使用流式输出
        async for chunk in agent.run(user_message, stream=True):
            if chunk["type"] == "chunk":
                # 发送流式内容块
                await websocket.send_json({
                    "type": "stream_chunk",
                    "data": {
                        "content": chunk["content"],
                        "full_response": chunk["full_response"]
                    }
                })
            elif chunk["type"] == "complete":
                # 发送完成消息
                await websocket.send_json({
                    "type": "complete",
                    "data": {
                        "content": chunk["content"]
                    }
                })
    except Exception as e:
        logger.error(f"Agent执行错误: {e}")
        await websocket.send_json({
            "type": "error",
            "data": {
                "message": f"处理消息时出错: {str(e)}"
            }
        })

@router.get("/ws/status")
async def websocket_status():
    """获取WebSocket连接状态"""
    return {
        "active_connections": len(active_connections),
        "clients": list(active_connections.keys())
    }