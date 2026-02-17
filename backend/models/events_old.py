"""
WebSocket事件模型
定义客户端和服务端之间通信的所有事件类型和数据结构
"""

from enum import Enum
from typing import Optional, Any, Dict, List
from datetime import datetime

class EventType(str, Enum):
    """事件类型枚举
    所有WebSocket消息的类型
    """
    # ===== 客户端发送的事件 =====
    START = "start"                    # 开始新对话
    MESSAGE = "message"                 # 发送消息
    APPROVE = "approve"                  # 确认（大纲或段落）
    APPROVE_SECTION = "approve_section"  # 确认段落（保留兼容）
    EDIT_SECTION = "edit_section"        # 修改段落
    REGENERATE = "regenerate"            # 重新生成段落
    CANCEL = "cancel"                    # 取消当前操作
    PING = "ping"                        # 心跳检测
    
    # ===== 服务端发送的事件 =====
    # 流式相关
    CHUNK = "chunk"                      # 流式输出片段
    COMPLETE = "complete"                # 完整响应
    
    # 状态同步
    SYNC = "sync"                         # 状态同步（断线重连用）
    STATE_CHANGE = "state_change"         # 状态变更通知
    
    # 段落相关
    SECTION_READY = "section_ready"       # 段落就绪（等待确认）
    SECTION_UPDATED = "section_updated"   # 段落已更新（修改后）
    
    # 任务进度
    PROGRESS = "progress"                 # 进度更新（如MCP任务进度）
    TASK_PROGRESS = "task_progress"       # 任务进度（别名）
    
    # 交互
    INTERRUPT = "interrupt"               # 需要用户输入
    PROMPT = "prompt"                     # 提示用户（问题+选项）
    
    # 完成
    REPORT_COMPLETED = "report_completed" # 报告全部完成
    
    # 错误/响应
    ERROR = "error"                        # 错误通知
    PONG = "pong"                          # 心跳响应


class ClientEvent:
    """客户端发送的事件基类
    所有从客户端发来的消息都继承这个结构
    """
    def __init__(
        self,
        type: EventType,          # 事件类型
        data: Dict[str, Any],     # 事件数据
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
        timestamp: Optional[datetime] = None,  # 事件发生时间
        request_id: Optional[str] = None  # 对应的请求ID（如果是响应）
    ):
        self.type = type
        self.data = data
        self.timestamp = timestamp or datetime.utcnow()
        self.request_id = request_id


# ==================== 客户端事件数据结构 ====================

class StartEventData:
    """开始对话事件
    客户端发送 {type: "start", data: {...}}
    """
    def __init__(
        self,
        title: Optional[str] = None,     # 对话标题
        context: Optional[Dict] = None   # 初始上下文
    ):
        self.title = title
        self.context = context or {}


class MessageEventData:
    """发送消息事件
    客户端发送 {type: "message", data: {...}}
    """
    def __init__(
        self,
        content: str,                    # 消息内容
        reply_to: Optional[str] = None   # 回复哪条消息
    ):
        self.content = content
        self.reply_to = reply_to


class ApproveEventData:
    """确认事件（用于确认大纲或段落）
    客户端发送 {type: "approve", data: {...}}
    """
    def __init__(
        self,
        section_id: Optional[str] = None,  # 有section_id表示确认段落，无则表示确认大纲
        feedback: Optional[str] = None     # 可选的反馈意见
    ):
        self.section_id = section_id
        self.feedback = feedback


class EditSectionEventData:
    """修改段落事件
    客户端发送 {type: "edit_section", data: {...}}
    """
    def __init__(
        self,
        section_id: str,                   # 要修改的段落ID
        instruction: str                    # 修改意见
    ):
        self.section_id = section_id
        self.instruction = instruction


class RegenerateEventData:
    """重写段落事件
    客户端发送 {type: "regenerate", data: {...}}
    """
    def __init__(
        self,
        section_id: str                    # 要重写的段落ID
    ):
        self.section_id = section_id


class PingEventData:
    """心跳事件
    客户端发送 {type: "ping", data: {...}}
    """
    def __init__(
        self,
        timestamp: Optional[str] = None
    ):
        self.timestamp = timestamp


# ==================== 服务端事件数据结构 ====================

class ChunkEventData:
    """流式片段事件
    服务端发送 {type: "chunk", data: {...}}
    """
    def __init__(
        self,
        text: str,                         # 本次发送的文本片段
        section_id: Optional[str] = None,   # 所属段落ID
        done: bool = False,                 # 是否最后一块
        message_id: Optional[str] = None    # 所属消息ID
    ):
        self.text = text
        self.section_id = section_id
        self.done = done
        self.message_id = message_id


class CompleteEventData:
    """完成事件
    服务端发送 {type: "complete", data: {...}}
    """
    def __init__(
        self,
        message_id: str,                     # 消息ID
        full_content: str,                    # 完整内容
        metadata: Optional[Dict] = None       # 元数据
    ):
        self.message_id = message_id
        self.full_content = full_content
        self.metadata = metadata or {}


class SyncEventData:
    """状态同步事件（断线重连）
    服务端发送 {type: "sync", data: {...}}
    """
    def __init__(
        self,
        type: str,                            # 同步类型: "connected", "history", "state"
        thread_id: Optional[str] = None,
        phase: Optional[str] = None,
        messages: Optional[List] = None,
        sections: Optional[List] = None,
        total: Optional[int] = None,
        shown: Optional[int] = None,
        title: Optional[str] = None,
        pending_question: Optional[str] = None,
        pending_options: Optional[List[str]] = None,
        **kwargs
    ):
        self.type = type
        self.thread_id = thread_id
        self.phase = phase
        self.messages = messages
        self.sections = sections
        self.total = total
        self.shown = shown
        self.title = title
        self.pending_question = pending_question
        self.pending_options = pending_options
        # 允许其他字段
        for k, v in kwargs.items():
            setattr(self, k, v)


class SectionReadyEventData:
    """段落就绪事件（等待用户确认）
    服务端发送 {type: "section_ready", data: {...}}
    """
    def __init__(
        self,
        section_id: str,                      # 段落ID
        title: str,                           # 段落标题
        content: str,                          # 段落内容
        question: str = "段落完成，您满意吗？",   # 提示问题
        options: List[str] = ["确认", "修改", "重写"]  # 选项按钮
    ):
        self.section_id = section_id
        self.title = title
        self.content = content
        self.question = question
        self.options = options


class PromptEventData:
    """提示事件（需要用户输入）
    服务端发送 {type: "prompt", data: {...}}
    """
    def __init__(
        self,
        question: str,                         # 问题
        options: List[str],                    # 选项按钮
        context: Optional[Dict] = None         # 上下文信息
    ):
        self.question = question
        self.options = options
        self.context = context or {}


class InterruptEventData:
    """中断事件（需要用户介入）
    服务端发送 {type: "interrupt", data: {...}}
    """
    def __init__(
        self,
        reason: str,                           # 中断原因
        section_id: Optional[str] = None,      # 关联的段落
        question: Optional[str] = None,         # 问题
        options: Optional[List[str]] = None     # 选项
    ):
        self.reason = reason
        self.section_id = section_id
        self.question = question
        self.options = options


class TaskProgressEventData:
    """任务进度事件
    服务端发送 {type: "task_progress", data: {...}}
    """
    def __init__(
        self,
        task_id: str,                          # 任务ID
        progress: float,                        # 0-1 进度
        message: str,                           # 状态消息
        status: Optional[str] = None            # 状态: "running", "completed", "failed"
    ):
        self.task_id = task_id
        self.progress = progress
        self.message = message
        self.status = status


class SectionUpdatedEventData:
    """段落更新事件（修改后）
    服务端发送 {type: "section_updated", data: {...}}
    """
    def __init__(
        self,
        section_id: str,                      # 段落ID
        content: str,                          # 新内容
        version: int,                          # 新版本号
        status: str                            # 新状态
    ):
        self.section_id = section_id
        self.content = content
        self.version = version
        self.status = status


class ReportCompletedEventData:
    """报告完成事件
    服务端发送 {type: "report_completed", data: {...}}
    """
    def __init__(
        self,
        total_sections: int,                   # 总段落数
        total_words: int,                       # 总字数
        export_formats: List[str] = ["markdown", "pdf"]  # 可导出格式
    ):
        self.total_sections = total_sections
        self.total_words = total_words
        self.export_formats = export_formats


class ErrorEventData:
    """错误事件
    服务端发送 {type: "error", data: {...}}
    """
    def __init__(
        self,
        code: str,                             # 错误码
        message: str,                           # 错误描述
        details: Optional[Dict] = None          # 详细信息
    ):
        self.code = code
        self.message = message
        self.details = details or {}


class PongEventData:
    """心跳响应事件
    服务端发送 {type: "pong", data: {...}}
    """
    def __init__(
        self,
        timestamp: str,                         # 服务器时间
        echo: Optional[Dict] = None             # 回显客户端数据
    ):
        self.timestamp = timestamp
        self.echo = echo



# 新增内容
# 新增事件	用途
# APPROVE	通用确认（可确认大纲或段落）
# INTERRUPT	需要用户介入时触发
# PROMPT	提示用户选择
# SECTION_UPDATED	段落修改后通知前端
# REPORT_COMPLETED	整个报告完成
# STATE_CHANGE	状态变更通知
# TASK_PROGRESS	MCP任务进度