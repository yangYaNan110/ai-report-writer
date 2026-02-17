"""
WebSocket事件模型
纯数据模型，只定义数据结构，不包含方法
类似于前端的 TypeScript interface
"""

from enum import Enum
from typing import Optional, Any, Dict, List
from datetime import datetime
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


@dataclass
class ServerEvent:
    """服务端发送的事件基类"""
    type: EventType                         # 事件类型
    data: Dict[str, Any]                    # 事件数据
    timestamp: datetime = field(default_factory=datetime.utcnow)  # 事件时间
    request_id: Optional[str] = None         # 请求ID


# ==================== 客户端事件数据结构 ====================

@dataclass
class StartEventData:
    """开始对话事件"""
    title: Optional[str] = None        # 对话标题
    context: Dict[str, Any] = field(default_factory=dict)  # 初始上下文


@dataclass
class MessageEventData:
    """发送消息事件"""
    content: str                        # 消息内容
    reply_to: Optional[str] = None      # 回复哪条消息


@dataclass
class ApproveEventData:
    """确认事件（用于确认大纲或段落）"""
    section_id: Optional[str] = None    # 有值表示确认段落，无表示确认大纲
    feedback: Optional[str] = None      # 可选的反馈意见


@dataclass
class EditSectionEventData:
    """修改段落事件"""
    section_id: str                     # 要修改的段落ID
    instruction: str                     # 修改意见


@dataclass
class RegenerateEventData:
    """重写段落事件"""
    section_id: str                      # 要重写的段落ID


@dataclass
class PingEventData:
    """心跳事件"""
    timestamp: Optional[str] = None      # 客户端时间


# ==================== 服务端事件数据结构 ====================

@dataclass
class ChunkEventData:
    """流式片段事件"""
    text: str                            # 本次发送的文本片段
    section_id: Optional[str] = None     # 所属段落ID
    done: bool = False                   # 是否最后一块
    message_id: Optional[str] = None     # 所属消息ID


@dataclass
class CompleteEventData:
    """完成事件"""
    message_id: str                      # 消息ID
    full_content: str                    # 完整内容
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据


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


@dataclass
class SectionReadyEventData:
    """段落就绪事件（等待用户确认）"""
    section_id: str                      # 段落ID
    title: str                           # 段落标题
    content: str                         # 段落内容
    question: str = "段落完成，您满意吗？"   # 提示问题
    options: List[str] = field(default_factory=lambda: ["确认", "修改", "重写"])  # 选项


@dataclass
class PromptEventData:
    """提示事件（需要用户输入）"""
    question: str                        # 问题
    options: List[str] = field(default_factory=list)  # 选项按钮
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息


@dataclass
class InterruptEventData:
    """中断事件（需要用户介入）"""
    reason: str                          # 中断原因
    section_id: Optional[str] = None     # 关联的段落
    question: Optional[str] = None       # 问题
    options: List[str] = field(default_factory=list)  # 选项


@dataclass
class TaskProgressEventData:
    """任务进度事件"""
    task_id: str                         # 任务ID
    progress: float                      # 0-1 进度
    message: str                         # 状态消息
    status: Optional[str] = None         # 状态: "running", "completed", "failed"


@dataclass
class SectionUpdatedEventData:
    """段落更新事件（修改后）"""
    section_id: str                      # 段落ID
    content: str                         # 新内容
    version: int                         # 新版本号
    status: str                          # 新状态


@dataclass
class ReportCompletedEventData:
    """报告完成事件"""
    total_sections: int                  # 总段落数
    total_words: int                     # 总字数
    export_formats: List[str] = field(default_factory=lambda: ["markdown", "pdf"])  # 可导出格式


@dataclass
class ErrorEventData:
    """错误事件"""
    code: str                            # 错误码
    message: str                         # 错误描述
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息


@dataclass
class PongEventData:
    """心跳响应事件"""
    timestamp: str                       # 服务器时间
    echo: Optional[Dict] = None          # 回显客户端数据