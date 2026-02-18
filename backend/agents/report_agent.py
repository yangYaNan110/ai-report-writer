"""
基础Agno Agent
阶段1.1：只使用内置能力，无skills、无MCP
阶段2.2：增加Skill加载能力（可选）
"""
from agno.agent import Agent
from agno.models.dashscope import DashScope
from config.settings import settings  # 从settings获取配置
from typing import AsyncGenerator, Union, Dict, Any, List, Optional
from pathlib import Path
import logging
import os

# 配置日志
logger = logging.getLogger(__name__)

class ReportAgent:
    """
    基础报告写作Agent
    职责：处理基础的对话和写作任务，支持可选加载Skill
    """
    # 单例模式：类变量
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """单例模式：确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self, model_id: str = "qwen-plus", skill_names: Optional[List[str]] = None):
        """
        初始化Agent
        
        Args:
            model_id: 模型ID
            skill_names: 要加载的Skill名称列表，如 ["report-writing", "tool-usage-strategy"]
                         如果为None或空列表，则不加载任何Skill（保持基础功能）
        """

        # 单例模式：如果已经初始化过，直接返回
        if self._initialized:
            return
        # 从settings获取API Key
        api_key = settings.DASHSCOPE_API_KEY
        if not api_key:
            raise ValueError("❌ DASHSCOPE_API_KEY 环境变量未设置！请在.env文件中配置")
        
        # description = 个人简介（给用户看）
        # instructions = 员工手册（给Agent用）
        # 加载skills（如果指定了skill_names）
        
        # 基础指令
        
        self.agent = Agent(
            model=DashScope(
                id=model_id,
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
            instructions= [
                "你是一个交互式报告写作助手",
                "根据当前任务选择合适的技能指南",
                "回答要专业、客观、简洁",
                "不确定时如实告知，不编造信息",
                "保持友好的对话风格",
            ],
            skills = self._load_skills(skill_names) if skill_names else None

        )
        print(f"✅ Agent初始化完成，使用模型: {model_id}")
         # 标记为已初始化
        self._initialized = True
    
    def _load_skills(self, skill_names: List[str]) -> Optional[Any]:
        """
        加载指定的Skill文件
        
        Args:
            skill_names: Skill名称列表
            
        Returns:
            Skills对象或None（如果加载失败）
        """
        try:
            # 计算skills目录路径
            # 当前文件在: agents/report_agent.py
            # 项目根目录: agents/../../ (即项目根目录)
            current_file = Path(__file__).resolve()  # agents/report_agent.py
            project_root = current_file.parent.parent  # 项目根目录
            skills_dir = project_root / "skills"
            
            # 检查skills目录是否存在
            if not skills_dir.exists():
                logger.warning(f"⚠️ Skills目录不存在: {skills_dir}")
                print(f"⚠️ Skills目录不存在: {skills_dir}")
                return None
            
            # 确定要加载的Skill路径
            skill_paths = []
            for name in skill_names:
                skill_path = skills_dir / name
                if skill_path.exists() and skill_path.is_dir():
                    skill_paths.append(str(skill_path))
                    logger.info(f"找到Skill: {name} at {skill_path}")
                else:
                    logger.warning(f"⚠️ Skill不存在: {name}")
                    print(f"⚠️ Skill不存在: {name}，跳过")
            
            if not skill_paths:
                logger.info("没有找到任何有效的Skill")
                return None
            
            # 尝试加载Skills（兼容不同版本的Agno）
            return self._try_load_skills(skill_paths)
            
        except Exception as e:
            logger.error(f"加载Skills时出错: {e}")
            print(f"⚠️ 加载Skills时出错: {e}，将不使用Skill继续运行")
            return None
    
    def _try_load_skills(self, skill_paths: List[str]) -> Optional[Any]:
        """
        尝试不同的方式加载Skills（兼容不同Agno版本）
        
        Args:
            skill_paths: Skill目录路径列表
            
        Returns:
            Skills对象或None
        """
        # 方式1：尝试 agno.skills.Skills + LocalSkillsLoader
        try:
            from agno.skills import Skills
            from agno.skills.loaders.local import LocalSkillsLoader
            
            skills = Skills(loaders=[
                LocalSkillsLoader(path) for path in skill_paths
            ])
            logger.info(f"✅ 使用 LocalSkillsLoader 加载了 {len(skill_paths)} 个Skill")
            return skills
        except ImportError:
            logger.debug("方式1导入失败，尝试方式2")
        
        # 方式2：尝试 agno.skills.Skills + LocalSkills
        try:
            from agno.skills import Skills, LocalSkills
            
            skills = Skills(loaders=[
                LocalSkills(path) for path in skill_paths
            ])
            logger.info(f"✅ 使用 LocalSkills 加载了 {len(skill_paths)} 个Skill")
            return skills
        except ImportError:
            logger.debug("方式2导入失败，尝试方式3")
        
        # 方式3：尝试直接使用 Agno 的旧版本API
        try:
            from agno.skills import SkillSet
            
            skills = SkillSet.from_directories(skill_paths)
            logger.info(f"✅ 使用 SkillSet 加载了 {len(skill_paths)} 个Skill")
            return skills
        except ImportError:
            logger.debug("方式3导入失败")
        
        logger.warning("⚠️ 无法加载Skills：当前Agno版本可能不支持，或需要安装额外依赖")
        print("⚠️ 无法加载Skills，将使用基础功能继续运行")
        return None
    
    async def run(self, task: str, stream: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行任务（流式版本）
        
        Args:
            task: 任务描述
            stream: 是否流式输出
        
        Yields:
            流式输出的数据块
        """
        if stream:
            # 流式输出
            response = ""
            async for chunk in self.agent.arun(task, stream=True):
                if chunk.content:
                    response += chunk.content
                    yield {
                        "type": "chunk",
                        "content": chunk.content,
                        "full_response": response
                    }
            # 最后yield完整响应
            yield {
                "type": "complete",
                "content": response
            }
        else:
            # 非流式输出 - 这里不能用yield，需要另一个方法
            raise ValueError("非流式模式请使用 chat() 方法")
    
   
   


# 测试代码（直接运行此文件时执行）
if __name__ == "__main__":
    import asyncio
    from config.settings import settings
    
    async def test_agent():
        print("=" * 50)
        print("测试基础Agent")
        print("=" * 50)
        
        # 检查API Key是否配置
        if not settings.DASHSCOPE_API_KEY:
            print("❌ 请先在.env文件中配置 DASHSCOPE_API_KEY")
            return
        
        

        
        
        print("=" * 50)
        print("✅ 测试完成")
    
    asyncio.run(test_agent())