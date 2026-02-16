# models/events.py
"""
WebSocket事件模型
定义客户端和服务端之间通信的所有事件类型和数据结构
"""

from enum import Enum
from typing import Optional, Any, Dict
from datetime import datetime

class EventType(str, Enum):
    """事件类型枚举
    所有WebSocket消息的类型
    """
    # 客户端发送的事件
    START = "start"              # 开始新对话
    MESSAGE = "message"          # 发送消息
    APPROVE_SECTION = "approve_section"  # 确认段落
    EDIT_SECTION = "edit_section"        # 修改段落
    REGENERATE = "regenerate"    # 重新生成
    CANCEL = "cancel"            # 取消当前操作
    PING = "ping"                # 心跳检测
    
    # 服务端发送的事件
    CHUNK = "chunk"              # 流式输出片段
    COMPLETE = "complete"        # 完整响应
    SECTION_READY = "section_ready"  # 段落就绪（等待确认）
    SYNC = "sync"                # 状态同步（断线重连用）
    PROGRESS = "progress"        # 进度更新（如MCP任务进度）
    ERROR = "error"              # 错误通知
    PONG = "pong"                # 心跳响应

class ClientEvent:
    """客户端发送的事件基类
    所有从客户端发来的消息都继承这个结构
    """
    def __init__(
        self,
        type: EventType,          # 事件类型
        data: Dict[str, Any],     # 事件数据（具体内容根据type不同而变化）
        request_id: Optional[str] = None  # 请求ID，用于跟踪响应
    ):
        self.type = type
        self.data = data
        self.request_id = request_id

class ServerEvent:
    """服务端发送的事件基类
    所有从服务端发往客户端的消息都继承这个结构
    """
    def __init__(
        self,
        type: EventType,          # 事件类型
        data: Dict[str, Any],     # 事件数据
        timestamp: datetime,      # 事件发生时间
        request_id: Optional[str] = None  # 对应的请求ID（如果是响应）
    ):
        self.type = type
        self.data = data
        self.timestamp = timestamp
        self.request_id = request_id

# 以下是具体的事件数据结构定义（用于类型提示）

class StartEventData:
    """开始对话事件的数据结构
    客户端发送 {type: "start", data: {...}}
    """
    def __init__(
        self,
        title: Optional[str] = None,     # 对话标题（可选，不传则自动生成）
        context: Optional[Dict] = None   # 初始上下文（如上传的文件ID）
    ):
        self.title = title
        self.context = context

class MessageEventData:
    """发送消息事件的数据结构
    客户端发送 {type: "message", data: {...}}
    """
    def __init__(
        self,
        content: str,                    # 消息内容
        reply_to: Optional[str] = None   # 回复哪条消息（用于追问）
    ):
        self.content = content
        self.reply_to = reply_to

class ChunkEventData:
    """流式片段事件的数据结构
    服务端发送 {type: "chunk", data: {...}}
    """
    def __init__(
        self,
        text: str,                        # 本次发送的文本片段
        done: bool = False,               # 是否最后一块
        message_id: Optional[str] = None  # 所属消息ID
    ):
        self.text = text
        self.done = done
        self.message_id = message_id

class ErrorEventData:
    """错误事件的数据结构
    服务端发送 {type: "error", data: {...}}
    """
    def __init__(
        self,
        code: str,                         # 错误码（如"INVALID_ACTION"）
        message: str,                       # 错误描述
        details: Optional[Dict] = None      # 详细信息（用于调试）
    ):
        self.code = code
        self.message = message
        self.details = details