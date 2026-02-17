"""
对话状态模型
纯数据模型，只定义数据结构，包含必要的序列化方法
"""

from enum import Enum
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


class Phase(str, Enum):
    """对话阶段枚举"""
    PLANNING = "planning"              # 规划大纲
    REVIEWING_PLAN = "reviewing_plan"  # 确认大纲
    WRITING = "writing"                 # 写作中
    REVIEWING_SECTION = "reviewing_section"  # 确认段落
    EDITING = "editing"                 # 修改中
    COMPLETED = "completed"             # 报告完成
    ERROR = "error"                     # 错误


class SectionStatus(str, Enum):
    """段落状态枚举"""
    DRAFT = "draft"          # 草稿（刚生成）
    PENDING = "pending"      # 待确认（等待用户反馈）
    CONFIRMED = "confirmed"  # 已确认 ✅
    EDITING = "editing"      # 修改中
    REJECTED = "rejected"    # 需修改


class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"               # 用户
    ASSISTANT = "assistant"     # AI
    SYSTEM = "system"           # 系统


@dataclass
class Message:
    """单条消息模型"""
    id: str                              # 消息唯一ID
    role: MessageRole                    # 发送者角色
    content: str                          # 消息内容
    created_at: datetime                  # 发送时间
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    section_id: Optional[str] = None      # 关联的段落ID
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "section_id": self.section_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典创建（用于反序列化）"""
        return cls(
            id=data["id"],
            role=MessageRole(data["role"]),
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"],
            metadata=data.get("metadata", {}),
            section_id=data.get("section_id")
        )


@dataclass
class Section:
    """报告段落模型"""
    id: str                               # 段落唯一ID
    title: str                             # 段落标题
    content: str = ""                       # 段落内容
    status: SectionStatus = SectionStatus.DRAFT  # 状态
    order: int = 0                          # 排序序号
    version: int = 1                        # 版本号
    created_at: Optional[datetime] = None   # 创建时间
    updated_at: Optional[datetime] = None   # 更新时间
    comments: List[str] = field(default_factory=list)  # 修改意见
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "status": self.status.value,
            "order": self.order,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "comments": self.comments,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Section":
        """从字典创建（用于反序列化）"""
        return cls(
            id=data["id"],
            title=data["title"],
            content=data.get("content", ""),
            status=SectionStatus(data.get("status", "draft")),
            order=data.get("order", 0),
            version=data.get("version", 1),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            comments=data.get("comments", []),
            metadata=data.get("metadata", {})
        )


@dataclass
class Conversation:
    """对话主模型"""
    # 基础信息
    id: str                                # 对话唯一ID
    title: str                              # 对话标题
    phase: Phase                            # 当前阶段
    created_at: datetime                    # 创建时间
    updated_at: datetime                    # 更新时间
    
    # 内容
    messages: List[Message] = field(default_factory=list)  # 历史消息
    sections: List[Section] = field(default_factory=list)  # 报告段落
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文数据
    
    # 交互状态
    current_section_id: Optional[str] = None    # 当前正在写的段落ID
    pending_question: Optional[str] = None      # 当前等待用户回答的问题
    pending_options: List[str] = field(default_factory=list)  # 选项按钮
    
    # 编辑状态
    edit_target_id: Optional[str] = None        # 正在修改的段落ID
    edit_instruction: Optional[str] = None      # 修改意见
    paused_section_id: Optional[str] = None     # 被暂停的段落ID
    
    # 扩展字段
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "title": self.title,
            "phase": self.phase.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
            "sections": [s.to_dict() for s in self.sections],
            "context": self.context,
            "current_section_id": self.current_section_id,
            "pending_question": self.pending_question,
            "pending_options": self.pending_options,
            "edit_target_id": self.edit_target_id,
            "edit_instruction": self.edit_instruction,
            "paused_section_id": self.paused_section_id,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conversation":
        """从字典创建（用于反序列化）"""
        return cls(
            id=data["id"],
            title=data["title"],
            phase=Phase(data["phase"]),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data["updated_at"], str) else data["updated_at"],
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            sections=[Section.from_dict(s) for s in data.get("sections", [])],
            context=data.get("context", {}),
            current_section_id=data.get("current_section_id"),
            pending_question=data.get("pending_question"),
            pending_options=data.get("pending_options", []),
            edit_target_id=data.get("edit_target_id"),
            edit_instruction=data.get("edit_instruction"),
            paused_section_id=data.get("paused_section_id"),
            metadata=data.get("metadata", {})
        )