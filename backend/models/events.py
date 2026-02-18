"""
WebSocket事件模型
纯数据模型，只定义数据结构，包含必要的序列化方法
"""

from enum import Enum
from typing import Optional, Any, Dict, List
from datetime import datetime, timezone
from dataclasses import dataclass, field


class EventType(str, Enum):
    """事件类型枚举"""
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
    PROGRESS = "progress"                 # 进度更新
    TASK_PROGRESS = "task_progress"       # 任务进度
    
    # 交互
    INTERRUPT = "interrupt"               # 需要用户输入
    PROMPT = "prompt"                     # 提示用户（问题+选项）
    
    # 完成
    REPORT_COMPLETED = "report_completed" # 报告全部完成
    
    # 错误/响应
    ERROR = "error"                        # 错误通知
    PONG = "pong"                          # 心跳响应


@dataclass
class ClientEvent:
    """客户端发送的事件基类"""
    type: EventType                         # 事件类型
    data: Dict[str, Any]                    # 事件数据
    request_id: Optional[str] = None         # 请求ID
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于发送）"""
        return {
            "type": self.type.value,
            "data": self.data,
            "request_id": self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientEvent":
        """从字典创建（用于接收）"""
        return cls(
            type=EventType(data["type"]),
            data=data.get("data", {}),
            request_id=data.get("request_id")
        )


@dataclass
class ServerEvent:
    """服务端发送的事件基类"""
    type: EventType                         # 事件类型
    data: Dict[str, Any]                    # 事件数据
    timestamp: datetime = field(default_factory=datetime.now(timezone.utc))  # 事件时间
    request_id: Optional[str] = None    
    section: Optional[str] = None     # 当前的内容类型
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于发送）"""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "section": self.section
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerEvent":
        """从字典创建（用于接收）"""
        return cls(
            type=EventType(data["type"]),
            data=data.get("data", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc),
            request_id=data.get("request_id"),
            section=data.get("section")
        )


# ==================== 客户端事件数据结构 ====================

@dataclass
class StartEventData:
    """开始对话事件"""
    title: Optional[str] = None        # 对话标题
    context: Dict[str, Any] = field(default_factory=dict)  # 初始上下文
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "context": self.context
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StartEventData":
        return cls(
            title=data.get("title"),
            context=data.get("context", {})
        )


@dataclass
class MessageEventData:
    """发送消息事件"""
    content: str                        # 消息内容
    reply_to: Optional[str] = None      # 回复哪条消息
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "reply_to": self.reply_to
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageEventData":
        return cls(
            content=data["content"],
            reply_to=data.get("reply_to")
        )


@dataclass
class ApproveEventData:
    """确认事件（用于确认大纲或段落）"""
    section_id: Optional[str] = None    # 有值表示确认段落，无表示确认大纲
    feedback: Optional[str] = None      # 可选的反馈意见
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "feedback": self.feedback
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApproveEventData":
        return cls(
            section_id=data.get("section_id"),
            feedback=data.get("feedback")
        )


@dataclass
class EditSectionEventData:
    """修改段落事件"""
    section_id: str                     # 要修改的段落ID
    instruction: str                     # 修改意见
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "instruction": self.instruction
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EditSectionEventData":
        return cls(
            section_id=data["section_id"],
            instruction=data.get("instruction", "")
        )


@dataclass
class RegenerateEventData:
    """重写段落事件"""
    section_id: str                      # 要重写的段落ID
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegenerateEventData":
        return cls(
            section_id=data["section_id"]
        )


@dataclass
class PingEventData:
    """心跳事件"""
    timestamp: Optional[str] = None      # 客户端时间
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PingEventData":
        return cls(
            timestamp=data.get("timestamp")
        )


# ==================== 服务端事件数据结构 ====================

@dataclass
class ChunkEventData:
    """流式片段事件"""
    text: str                            # 本次发送的文本片段
    section_id: Optional[str] = None     # 所属段落ID
    done: bool = False                   # 是否最后一块
    message_id: Optional[str] = None     # 所属消息ID
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "section_id": self.section_id,
            "done": self.done,
            "message_id": self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkEventData":
        return cls(
            text=data["text"],
            section_id=data.get("section_id"),
            done=data.get("done", False),
            message_id=data.get("message_id")
        )


@dataclass
class CompleteEventData:
    """完成事件"""
    message_id: str                      # 消息ID
    full_content: str                    # 完整内容
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "full_content": self.full_content,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompleteEventData":
        return cls(
            message_id=data["message_id"],
            full_content=data["full_content"],
            metadata=data.get("metadata", {})
        )


@dataclass
class SyncEventData:
    """状态同步事件（断线重连）"""
    type: str                            # 同步类型: "connected", "history", "state"
    thread_id: Optional[str] = None
    phase: Optional[str] = None
    messages: Optional[List] = None
    sections: Optional[List] = None
    total: Optional[int] = None
    shown: Optional[int] = None
    title: Optional[str] = None
    pending_question: Optional[str] = None
    pending_options: List[str] = field(default_factory=list)
    # 允许其他字段
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "thread_id": self.thread_id,
            "phase": self.phase,
            "messages": self.messages,
            "sections": self.sections,
            "total": self.total,
            "shown": self.shown,
            "title": self.title,
            "pending_question": self.pending_question,
            "pending_options": self.pending_options,
            **self.extra
        }
        # 移除 None 值
        return {k: v for k, v in result.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncEventData":
        extra = {k: v for k, v in data.items() 
                 if k not in ["type", "thread_id", "phase", "messages", "sections", 
                              "total", "shown", "title", "pending_question", "pending_options"]}
        return cls(
            type=data["type"],
            thread_id=data.get("thread_id"),
            phase=data.get("phase"),
            messages=data.get("messages"),
            sections=data.get("sections"),
            total=data.get("total"),
            shown=data.get("shown"),
            title=data.get("title"),
            pending_question=data.get("pending_question"),
            pending_options=data.get("pending_options", []),
            extra=extra
        )


@dataclass
class SectionReadyEventData:
    """段落就绪事件（等待用户确认）"""
    section_id: str                      # 段落ID
    title: str                           # 段落标题
    content: str                         # 段落内容
    question: str = "段落完成，您满意吗？"   # 提示问题
    options: List[str] = field(default_factory=lambda: ["确认", "修改", "重写"])  # 选项
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content,
            "question": self.question,
            "options": self.options
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionReadyEventData":
        return cls(
            section_id=data["section_id"],
            title=data["title"],
            content=data["content"],
            question=data.get("question", "段落完成，您满意吗？"),
            options=data.get("options", ["确认", "修改", "重写"])
        )


@dataclass
class PromptEventData:
    """提示事件（需要用户输入）"""
    question: str                        # 问题
    options: List[str] = field(default_factory=list)  # 选项按钮
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "options": self.options,
            "context": self.context
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptEventData":
        return cls(
            question=data["question"],
            options=data.get("options", []),
            context=data.get("context", {})
        )


@dataclass
class InterruptEventData:
    """中断事件（需要用户介入）"""
    reason: str                          # 中断原因
    section_id: Optional[str] = None     # 关联的段落
    question: Optional[str] = None       # 问题
    options: List[str] = field(default_factory=list)  # 选项
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "section_id": self.section_id,
            "question": self.question,
            "options": self.options
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterruptEventData":
        return cls(
            reason=data["reason"],
            section_id=data.get("section_id"),
            question=data.get("question"),
            options=data.get("options", [])
        )


@dataclass
class TaskProgressEventData:
    """任务进度事件"""
    task_id: str                         # 任务ID
    progress: float                      # 0-1 进度
    message: str                         # 状态消息
    status: Optional[str] = None         # 状态: "running", "completed", "failed"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "progress": self.progress,
            "message": self.message,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskProgressEventData":
        return cls(
            task_id=data["task_id"],
            progress=data["progress"],
            message=data["message"],
            status=data.get("status")
        )


@dataclass
class SectionUpdatedEventData:
    """段落更新事件（修改后）"""
    section_id: str                      # 段落ID
    content: str                         # 新内容
    version: int                         # 新版本号
    status: str                          # 新状态
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "content": self.content,
            "version": self.version,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionUpdatedEventData":
        return cls(
            section_id=data["section_id"],
            content=data["content"],
            version=data["version"],
            status=data["status"]
        )


@dataclass
class ReportCompletedEventData:
    """报告完成事件"""
    total_sections: int                  # 总段落数
    total_words: int                     # 总字数
    export_formats: List[str] = field(default_factory=lambda: ["markdown", "pdf"])  # 可导出格式
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sections": self.total_sections,
            "total_words": self.total_words,
            "export_formats": self.export_formats
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportCompletedEventData":
        return cls(
            total_sections=data["total_sections"],
            total_words=data["total_words"],
            export_formats=data.get("export_formats", ["markdown", "pdf"])
        )


@dataclass
class ErrorEventData:
    """错误事件"""
    code: str                            # 错误码
    message: str                         # 错误描述
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorEventData":
        return cls(
            code=data["code"],
            message=data["message"],
            details=data.get("details", {})
        )


@dataclass
class PongEventData:
    """心跳响应事件"""
    timestamp: str                       # 服务器时间
    echo: Optional[Dict] = None          # 回显客户端数据
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "echo": self.echo
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PongEventData":
        return cls(
            timestamp=data["timestamp"],
            echo=data.get("echo")
        )


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("🧪 测试事件模型序列化...")
    
    # 测试 StartEventData
    start = StartEventData(title="测试报告", context={"source": "test"})
    start_dict = start.to_dict()
    start2 = StartEventData.from_dict(start_dict)
    print(f"✅ StartEventData: {start.title} -> {start2.title}")
    
    # 测试 ClientEvent
    client_event = ClientEvent(
        type=EventType.START,
        data=start_dict,
        request_id="req_123"
    )
    client_dict = client_event.to_dict()
    client_event2 = ClientEvent.from_dict(client_dict)
    print(f"✅ ClientEvent: {client_event2.type.value}")
    
    # 测试 ServerEvent
    server_event = ServerEvent(
        type=EventType.PONG,
        data={"timestamp": "test"},
        request_id="req_123"
    )
    server_dict = server_event.to_dict()
    server_event2 = ServerEvent.from_dict(server_dict)
    print(f"✅ ServerEvent: {server_event2.type.value}")
    
    print("🎉 所有事件模型序列化测试通过")