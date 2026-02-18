"""
对话存储类 - 每个对话一个独立实例
使用纯数据模型，包含内存缓存和业务逻辑
"""
from typing import Optional, List, Dict, Any
from datetime import datetime,timezone
import json
import uuid

from store.database import Database
from store.utils import json_serializer
from models.state import (
    Conversation, Message, Section,
    Phase, SectionStatus, MessageRole
)
from api.controllers import websocket_controller  # 导入WebSocket控制器（阶段1.2）

import json
import re
import time
import random


class ConversationStore:
    """对话存储类 - 每个对话独立实例"""
    
    @classmethod
    async def create(cls, db: Database, thread_id: str):
        """异步工厂方法：创建实例并加载数据"""
        instance = cls(db, thread_id)
        await instance._load_from_db()
        return instance
    
    def __init__(self, db: Database, thread_id: str):
        self.db = db
        self.thread_id = thread_id
        self.conversation: Optional[Conversation] = None
    
    # ==================== 私有加载和保存方法 ====================
    
    async def _load_from_db(self):
        """从数据库加载数据到内存"""
        print(f"\n📚 [ConversationStore._load_from_db] 开始加载对话 {self.thread_id}")
        
        # 1. 加载对话基本信息
        conv_data = await self.db.get_conversation(self.thread_id)
        
        if conv_data:
            self.conversation = Conversation.from_dict(conv_data)
            print(f"   ✅ 找到现有对话: {self.thread_id}")
        else:
            # 创建新对话
            self.conversation = Conversation(
                id=self.thread_id,
                title="新对话",
                phase=Phase.PLANNING,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                messages=[],
                sections=[],
                context={}
            )
            # 保存到数据库
            await self.db.save_conversation_info(self.thread_id, self.conversation.to_dict())
            print(f"   📁 创建新对话: {self.thread_id}")
        
        # 2. 加载消息
        msg_data = await self.db.get_messages(self.thread_id)
        if msg_data:
            messages = []
            for m in msg_data:
                msg_dict = {k: v for k, v in m.items() if k != 'conversation_id'}
                messages.append(Message.from_dict(msg_dict))
            self.conversation.messages = messages
            print(f"   📨 加载了 {len(messages)} 条消息")
        else:
            self.conversation.messages = []
            print(f"   📨 没有消息")
        
        # 3. 加载段落
        sec_data = await self.db.get_sections(self.thread_id)
        if sec_data:
            sections = []
            for s in sec_data:
                sec_dict = {k: v for k, v in s.items() if k != 'conversation_id'}
                sections.append(Section.from_dict(sec_dict))
            self.conversation.sections = sections
            print(f"   📄 加载了 {len(sections)} 个段落")
        else:
            self.conversation.sections = []
            print(f"   📄 没有段落")
    
    async def _save(self):
        """保存当前状态到数据库"""
        print(f"\n💾 [ConversationStore._save] 保存对话 {self.thread_id}")
        print(f"   使用连接ID: {self.db.connection_id}")  # 添加这行！
        print(f"   连接对象ID: {id(self.db.connection)}")  # 添加这行！
        self.conversation.updated_at = datetime.now(timezone.utc)
        await self.db.save_conversation_info(self.thread_id, self.conversation.to_dict())
        print(f"   ✅ 对话信息已保存")
    
    # ==================== 消息操作 ====================
    
    async def add_message(
        self,
        role: MessageRole,
        content: str,
        section_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """添加消息"""
        print(f"\n📝 [ConversationStore.add_message] 添加消息到 {self.thread_id}")
        
        # 确保 conversation 存在
        if not self.conversation:
            await self._load_from_db()
        
        message = Message(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
            section_id=section_id
        )
        print(f"   消息ID: {message.id}")
        print(f"   角色: {role.value}")
        print(f"   内容: {content[:50]}...")
        
        # 1. 更新内存
        self.conversation.messages.append(message)
        print(f"   内存中现在有 {len(self.conversation.messages)} 条消息")
        
        # 2. 保存到数据库
        msg_dict = {
            "id": message.id,
            "role": message.role.value,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "metadata": message.metadata,
            "section_id": message.section_id
        }
        await self.db.save_message(self.thread_id, msg_dict)
        
        # 3. 更新对话时间并保存
        await self._save()
        
        # 4. 验证保存
        msgs = await self.db.get_messages(self.thread_id)
        print(f"   数据库中现在有 {len(msgs)} 条消息")
        
        return message
    
    def get_recent_messages(self, count: int = 10) -> List[Dict[str, str]]:
        """获取最近N条消息（用于Agent）"""
        if not self.conversation or not self.conversation.messages:
            return []
        recent = self.conversation.messages[-count:]
        return [
            {"role": m.role.value, "content": m.content}
            for m in recent
        ]
    
    # ==================== 段落操作 ====================
    
    async def add_section(
        self,
        title: str,
        content: str = "",
        order: Optional[int] = None,
        status: SectionStatus = SectionStatus.DRAFT
    ) -> Section:
        """添加段落"""
        if not self.conversation:
            await self._load_from_db()
        
        # 生成唯一的序号 ID
        # 组合：时间戳 + 随机数 + 序号
        timestamp = int(time.time() * 1000)
        random_num = random.randint(1000, 9999)
        section_id = f"sec-{timestamp}-{random_num}-{len(self.conversation.sections) + 1}"
        # section_id = f"sec-{len(self.conversation.sections) + 1}"
        
        section = Section(
            id=section_id,
            title=title,
            content=content,
            status=status,
            order=order or len(self.conversation.sections),
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            comments=[],
            metadata={}
        )
        
        self.conversation.sections.append(section)
        await self._save()
        
        # 同步到数据库
        await self.db.save_section(self.thread_id, {
            "id": section.id,
            "title": section.title,
            "content": section.content,
            "status": section.status.value,
            "order": section.order,
            "version": section.version,
            "created_at": section.created_at.isoformat(),
            "updated_at": section.updated_at.isoformat(),
            "comments": section.comments,
            "metadata": section.metadata
        })
        
        return section
    
    def get_section(self, section_id: str) -> Optional[Section]:
        """获取指定段落"""
        if not self.conversation:
            return None
        for s in self.conversation.sections:
            if s.id == section_id:
                return s
        return None
    
    # ==================== 业务逻辑 ====================
    async def generate_report_stream(self, topic: str):
        """流式生成报告大纲"""
        if not self.conversation:
            await self._load_from_db()
        
        self.conversation.title = topic
        self.conversation.phase = Phase.PLANNING
        
        prompt = f"""
        请为报告主题「{topic}」规划一个详细的大纲。

        要求：
        1. 遵循 report-writing Skill 规范
        2. 大纲需要包含3-5个主要章节
        3. 每个章节必须有明确的主题
        4. 以JSON数组格式返回，每个元素是章节标题
        5. 不要返回任何其他内容，只返回JSON数组

        示例输出格式：
        ["引言", "市场现状分析", "技术发展趋势", "应用案例", "结论与建议"]

        请生成大纲：
        """
        
        print(f"📋 流式生成大纲，主题: {topic}")
        
        agent = websocket_controller.get_agent()
        full_content = ""
        
        try:
            # 流式模式
            async for chunk in agent.run([{"role": "user", "content": prompt}], stream=True):
                if chunk.get("type") == "chunk":
                    text = chunk.get("content", "")
                    full_content += text
                    yield {
                        "type": "chunk",
                        "content": text,
                        "section": "outline",
                        "done": False
                    }
                elif chunk.get("type") == "complete":
                    full_content = chunk.get("content", "")
                    # 解析完整内容
                    sections = self._parse_outline_from_response(full_content)
                    
                    # 确保至少有3个章节
                    if not sections or len(sections) < 3:
                        print(f"⚠️ 解析出 {len(sections) if sections else 0} 个章节，使用默认大纲")
                        sections = ["引言", "主体", "结论"]
                    
                    # 创建大纲段落
                    created_sections = []
                    for i, title in enumerate(sections):
                        section = await self.add_section(
                            title=title,
                            order=i+1,
                            status=SectionStatus.DRAFT
                        )
                        created_sections.append(section)
                        print(f"   📄 创建段落: {title}")
                    
                    # 设置等待用户确认
                    self.conversation.pending_question = "大纲已生成，您满意吗？"
                    self.conversation.pending_options = ["确认", "修改大纲"]
                    await self._save()
                    print("x"* 50)
                    # 发送完成信号
                    yield {
                        "type": "outline_complete",
                        "full_content": full_content,
                        "sections": [s.to_dict() for s in created_sections],
                        "pending_question": self.conversation.pending_question,
                        "pending_options": self.conversation.pending_options
                    }
                    
        except Exception as e:
            print(f"❌ 调用Agent失败: {e}")
            yield {
                "type": "error",
                "message": str(e)
            }


    async def generate_report(self, topic: str) -> List[Section]:
        """非流式生成报告大纲（直接返回段落列表）"""
        if not self.conversation:
            await self._load_from_db()
        
        self.conversation.title = topic
        self.conversation.phase = Phase.PLANNING
        
        prompt = f"""
    请为报告主题「{topic}」规划一个详细的大纲。

    要求：
    1. 遵循 report-writing Skill 规范
    2. 大纲需要包含3-5个主要章节
    3. 每个章节必须有明确的主题
    4. 以JSON数组格式返回，每个元素是章节标题
    5. 不要返回任何其他内容，只返回JSON数组

    示例输出格式：
    ["引言", "市场现状分析", "技术发展趋势", "应用案例", "结论与建议"]

    请生成大纲：
    """
        
        print(f"📋 非流式生成大纲，主题: {topic}")
        
        agent = websocket_controller.get_agent()
        sections = ["引言", "主体", "结论"]  # 默认值
        
        try:
            # 非流式模式
            async for response in agent.run([{"role": "user", "content": prompt}], stream=False):
                if response.get("type") == "complete":
                    content = response.get("content", "")
                    print(f"📥 Agent返回: {content[:200]}...")
                    sections = self._parse_outline_from_response(content)
                    
                    if not sections or len(sections) < 3:
                        print(f"⚠️ 解析出 {len(sections) if sections else 0} 个章节，使用默认大纲")
                        sections = ["引言", "主体", "结论"]
                    break
        except Exception as e:
            print(f"❌ 调用Agent失败: {e}")
        
        # 创建大纲段落
        created_sections = []
        for i, title in enumerate(sections):
            section = await self.add_section(
                title=title,
                order=i+1,
                status=SectionStatus.DRAFT
            )
            created_sections.append(section)
            print(f"   📄 创建段落: {title}")
        
        # 设置等待用户确认
        self.conversation.pending_question = "大纲已生成，您满意吗？"
        self.conversation.pending_options = ["确认", "修改大纲"]
        
        await self._save()
        
        return created_sections

    def _parse_outline_from_response(self, content: str) -> List[str]:
        """从Agent响应中解析大纲"""
    
        
        # 尝试直接解析JSON
        try:
            # 查找JSON数组
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                sections = json.loads(json_match.group())
                if isinstance(sections, list) and all(isinstance(s, str) for s in sections):
                    return sections
        except:
            pass
        
        # 尝试按行解析（每行一个章节）
        lines = content.strip().split('\n')
        sections = []
        for line in lines:
            # 去除序号和标点
            cleaned = re.sub(r'^\d+[\.\)、]\s*', '', line.strip())
            cleaned = re.sub(r'^[-\*]\s*', '', cleaned)
            if cleaned and len(cleaned) < 50 and not cleaned.startswith('```'):
                sections.append(cleaned)
        
        if len(sections) >= 3:
            return sections
        
        return []
    

    async def approve_plan(self):
        """确认大纲，开始写作"""
        if not self.conversation:
            await self._load_from_db()
            
        self.conversation.phase = Phase.WRITING
        self.conversation.pending_question = None
        self.conversation.pending_options = []
        await self._save()
        
        # 开始写第一段
        await self._write_next_section()
    
    async def _write_next_section(self):
        """写下一个未完成的段落"""
        if not self.conversation:
            return
            
        for section in self.conversation.sections:
            if section.status == SectionStatus.DRAFT and not section.content:
                self.conversation.current_section_id = section.id
                await self._write_section(section)
                return
        
        # 所有段落都完成了
        self.conversation.phase = Phase.COMPLETED
        self.conversation.current_section_id = None
        await self._save()
    
    async def _write_section(self, section: Section):
        """写单个段落"""
        section.content = f"这是{section.title}的内容。这里是详细的论述和分析。"
        section.updated_at = datetime.now(timezone.utc)
        
        self.conversation.phase = Phase.REVIEWING_SECTION
        self.conversation.pending_question = f"{section.title}完成，您满意吗？"
        self.conversation.pending_options = ["确认", "修改", "重写"]
        
        await self._save()
    
    async def approve_section(self, section_id: str):
        """确认段落"""
        section = self.get_section(section_id)
        if section:
            section.status = SectionStatus.CONFIRMED
            section.updated_at = datetime.now(timezone.utc)
            
            self.conversation.pending_question = None
            self.conversation.pending_options = []
            
            await self._save()
            
            # 继续写下一段
            await self._write_next_section()
    
    async def edit_section(self, section_id: str, instruction: str) -> str:
        """修改段落"""
        section = self.get_section(section_id)
        if not section:
            return ""
        
        section.status = SectionStatus.EDITING
        self.conversation.edit_target_id = section_id
        self.conversation.edit_instruction = instruction
        await self._save()
        
        # 模拟修改内容
        new_content = f"{section.content}\n\n[根据意见修改: {instruction}]"
        section.content = new_content
        section.version += 1
        section.status = SectionStatus.PENDING
        section.updated_at = datetime.now(timezone.utc)
        
        self.conversation.edit_target_id = None
        self.conversation.edit_instruction = None
        self.conversation.pending_question = f"{section.title}修改完成，您满意吗？"
        self.conversation.pending_options = ["确认", "再次修改"]
        
        await self._save()
        
        return new_content
    
    async def regenerate_section(self, section_id: str):
        """重写段落"""
        section = self.get_section(section_id)
        if section:
            section.content = ""
            section.status = SectionStatus.DRAFT
            section.version += 1
            section.updated_at = datetime.now(timezone.utc)
            
            self.conversation.current_section_id = section_id
            await self._save()
            
            await self._write_section(section)
    
    # ==================== 工具方法 ====================
    
    def get_phase(self) -> str:
        """获取当前阶段"""
        if not self.conversation:
            return "unknown"
        return self.conversation.phase.value
    
    @property
    def messages(self) -> List[Message]:
        """获取消息列表"""
        if not self.conversation:
            return []
        return self.conversation.messages
    
    @property
    def sections(self) -> List[Section]:
        """获取段落列表"""
        if not self.conversation:
            return []
        return self.conversation.sections