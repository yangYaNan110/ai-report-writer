# models/state.py
"""
对话状态模型
定义整个对话的生命周期状态和数据结构
"""

from enum import Enum
from datetime import datetime
from typing import List, Optional, Dict, Any

class Phase(str, Enum):
    """对话阶段枚举
    定义对话当前所处的阶段
    """
    PLANNING = "planning"      # 规划阶段：AI正在思考写作计划
    WRITING = "writing"         # 写作阶段：正在生成报告内容
    REVIEWING = "reviewing"     # 审核阶段：等待用户确认/修改
    COMPLETED = "completed"     # 完成阶段：报告已定稿
    ERROR = "error"             # 错误阶段：发生异常

class MessageRole(str, Enum):
    """消息角色枚举
    区分消息是谁发的
    """
    USER = "user"               # 用户发送的消息
    ASSISTANT = "assistant"      # AI发送的消息
    SYSTEM = "system"            # 系统发送的通知/状态更新

class Message:
    """单条消息模型
    代表对话中的一条消息，可以是用户发的、AI回的、或系统通知
    """
    def __init__(
        self,
        id: str,                 # 消息唯一ID，用于定位和引用
        role: MessageRole,        # 发送者角色（user/assistant/system）
        content: str,             # 消息内容（文本）
        created_at: datetime,     # 发送时间
        metadata: Optional[Dict[str, Any]] = None  # 附加元数据（如token用量、模型名称等）
    ):
        self.id = id
        self.role = role
        self.content = content
        self.created_at = created_at
        self.metadata = metadata or {}

class Section:
    """报告段落模型
    代表报告中的一个章节/段落，支持逐段确认修改
    """
    def __init__(
        self,
        id: str,                  # 段落唯一ID
        title: str,                # 段落标题（如"第一章"、"摘要"）
        content: str,              # 段落内容
        status: str = "draft",     # 状态：draft(草稿)/pending(待确认)/confirmed(已确认)/rejected(需修改)
        order: int = 0,            # 排序序号，用于调整段落顺序
        created_at: Optional[datetime] = None,      # 创建时间
        updated_at: Optional[datetime] = None,      # 最后更新时间
        comments: Optional[List[str]] = None  # 用户修改意见/评论
    ):
        self.id = id
        self.title = title
        self.content = content
        self.status = status
        self.order = order
        self.created_at = created_at
        self.updated_at = updated_at
        self.comments = comments or []

class Conversation:
    """对话主模型
    代表一次完整的报告写作对话
    """
    def __init__(
        self,
        id: str,                   # 对话唯一ID（对应WebSocket的thread_id）
        title: str,                 # 对话标题（如"2024年市场分析报告"）
        phase: Phase,               # 当前所处阶段（planning/writing等）
        messages: List[Message],    # 历史消息列表
        sections: List[Section],    # 生成的报告段落（空表示还没开始写）
        context: Dict[str, Any],    # 上下文数据（上传的文件内容、参考信息等）
        created_at: datetime,       # 对话创建时间
        updated_at: datetime,       # 最后活动时间
        metadata: Optional[Dict[str, Any]] = None  # 扩展字段（如模型参数、用户偏好等）
    ):
        self.id = id
        self.title = title
        self.phase = phase
        self.messages = messages
        self.sections = sections
        self.context = context
        self.created_at = created_at
        self.updated_at = updated_at
        self.metadata = metadata or {}


# 测试代码（可以先写在文件末尾，后面删掉）
if __name__ == "__main__":
    # 测试创建对话
    conv = Conversation(
        id="test-123",
        title="测试报告",
        phase=Phase.PLANNING,
        messages=[],
        sections=[],
        context={},
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    print(conv)