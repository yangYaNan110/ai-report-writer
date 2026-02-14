"""
基础Agno Agent
阶段1.1：只使用内置能力，无skills、无MCP
"""
from agno.agent import Agent
from agno.models.dashscope import DashScope
from config.settings import settings  # 从settings获取配置
from typing import AsyncGenerator, Union, Dict, Any

class ReportAgent:
    """
    基础报告写作Agent
    职责：处理基础的对话和写作任务
    """
    
    def __init__(self, model_id: str = "qwen-plus"):
        # 从settings获取API Key
        api_key = settings.DASHSCOPE_API_KEY
        if not api_key:
            raise ValueError("❌ DASHSCOPE_API_KEY 环境变量未设置！请在.env文件中配置")
        
        # description = 个人简介（给用户看）
        # instructions = 员工手册（给Agent用）
        
        self.agent = Agent(
            # 基础信息
            name="报告写作助手",
            description="我是一个专业的报告写作助手，可以帮助你撰写技术报告、市场分析、学术综述等各种类型的报告。",
            
            # 模型配置 - 使用通义千问
            model=DashScope(
                id=model_id,
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
            
            # 基础指令（员工手册）
            instructions=[
                "你是一个专业的报告写作助手",
                "回答要专业、客观、简洁",
                "使用Markdown格式组织内容",
                "不确定时如实告知，不编造信息",
                "保持友好的对话风格",
            ],
            
            # 基础配置
            markdown=True,  # 启用Markdown输出
            
            # 记忆管理（后续会用）
            # db=SqliteDb(db_file="data/agent_sessions.db"),
            # add_history_to_context=True,
            # num_history_messages=5,
        )
        
        print(f"✅ Agent初始化完成，使用模型: {model_id}")
    
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
    
    async def chat(self, message: str) -> str:
        """
        简单的对话方法（非流式）
        """
        response = await self.agent.arun(message)
        return response.content if hasattr(response, 'content') else str(response)
    
    async def run_non_stream(self, task: str) -> Dict[str, Any]:
        """
        非流式执行任务
        """
        response = await self.agent.arun(task)
        return {
            "type": "complete",
            "content": response.content if hasattr(response, 'content') else str(response)
        }


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
        
        # 初始化Agent
        agent = ReportAgent()
        
        # 测试简单对话（非流式）
        print("\n1. 测试简单对话（非流式）：")
        response = await agent.chat("你好，请简单介绍一下自己")
        print(f"Agent: {response}")
        
        # 测试非流式run方法
        print("\n2. 测试非流式run方法：")
        result = await agent.run_non_stream("用一句话解释什么是人工智能")
        print(f"Agent: {result['content']}")
        
        # 测试流式输出
        print("\n3. 测试流式输出：")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run("用一句话解释什么是机器学习", stream=True):
            if chunk["type"] == "chunk":
                print(chunk["content"], end="", flush=True)
        print("\n")
        
        print("=" * 50)
        print("✅ 测试完成")
    
    asyncio.run(test_agent())