# 目前已经有了 用户主动打断 ai。
# 还缺少 ai等待用户决策
# 可以使用以下策略
import asyncio
import websockets
import json
from enum import Enum
from typing import Optional, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class State(Enum):
    """定义所有可能的状态"""
    IDLE = "idle"                    # 空闲状态
    EXECUTING = "executing"           # 执行中
    AWAITING_USER = "awaiting_user"   # 等待用户决策
    COMPLETED = "completed"           # 已完成
    INTERRUPTED = "interrupted"       # 被打断

class AgentWorkflow:
    """状态机工作流"""
    
    def __init__(self, websocket):
        self.websocket = websocket
        self.state = State.IDLE
        self.context: Dict[str, Any] = {
            "step": 0,
            "history": [],
            "pending_question": None,
            "current_task": None
        }
        self.pending_future: Optional[asyncio.Future] = None
        
    async def process_message(self, message: str):
        """处理用户消息 - 状态驱动的核心"""
        logger.info(f"当前状态: {self.state.value}, 收到消息: {message}")
        
        # 根据当前状态处理消息
        if self.state == State.IDLE:
            # 空闲状态，开始新任务
            await self.start_workflow(message)
            
        elif self.state == State.EXECUTING:
            # 执行中收到消息 - 这是主动打断！
            await self.handle_interrupt(message)
            
        elif self.state == State.AWAITING_USER:
            # 等待用户决策 - 处理用户的回复
            await self.handle_user_response(message)
            
        elif self.state == State.INTERRUPTED:
            # 已打断状态，可以重新开始或继续
            if message == "继续":
                await self.resume_workflow()
            else:
                await self.start_workflow(message)
    
    async def start_workflow(self, initial_input: str):
        """开始新的工作流"""
        self.state = State.EXECUTING
        self.context = {
            "step": 1,
            "history": [f"开始: {initial_input}"],
            "initial_input": initial_input
        }
        
        # 启动执行任务
        self.context["current_task"] = asyncio.create_task(
            self.execute_workflow()
        )
        
        await self.websocket.send_json({
            "type": "status",
            "content": f"开始执行任务: {initial_input}"
        })
    
    async def execute_workflow(self):
        """实际的工作流执行逻辑"""
        try:
            # 步骤1：执行一些操作
            await self.send_message("步骤1: 正在分析需求...")
            await asyncio.sleep(1)  # 模拟工作
            
            # 步骤2：执行一些操作
            await self.send_message("步骤2: 正在生成大纲...")
            await asyncio.sleep(1)
            
            # ⭐ 决策点：需要询问用户是否继续
            await self.ask_user_decision(
                question="大纲已生成，是否继续写报告？",
                options=["继续", "修改", "中断"]
            )
            
            # 注意：执行到这里会暂停，不会继续往下走
            # 因为 ask_user_decision 会等待用户回复
            
            # 步骤3：用户选择"继续"后才会执行到这里
            await self.send_message("步骤3: 开始撰写报告...")
            await asyncio.sleep(1)
            
            # 又一个决策点
            await self.ask_user_decision(
                question="第一章已完成，是否继续写第二章？",
                options=["继续", "修改第一章", "中断"]
            )
            
            # 步骤4：继续执行...
            await self.send_message("步骤4: 完成所有章节...")
            
            # 完成
            self.state = State.COMPLETED
            await self.send_message("✅ 报告已完成！", msg_type="complete")
            
        except asyncio.CancelledError:
            logger.info("工作流被取消")
            self.state = State.INTERRUPTED
            await self.send_message("⏸️ 工作流已中断", msg_type="interrupt")
        except Exception as e:
            logger.error(f"工作流出错: {e}")
            self.state = State.IDLE
            await self.send_message(f"❌ 错误: {e}", msg_type="error")
    
    async def ask_user_decision(self, question: str, options: list):
        """询问用户决策 - 关键方法！"""
        
        # 保存当前问题到上下文
        self.context["pending_question"] = {
            "question": question,
            "options": options
        }
        
        # 创建 Future，等待用户回复
        self.pending_future = asyncio.Future()
        
        # 改变状态
        self.state = State.AWAITING_USER
        
        # 发送问题给用户
        await self.websocket.send_json({
            "type": "question",
            "content": question,
            "options": options
        })
        
        # ⭐ 关键：这里会暂停，等待用户回复
        # 用户回复后，handle_user_response 会设置 future 的结果
        user_response = await self.pending_future
        
        # 用户回复后，从这里继续执行
        logger.info(f"收到用户决策: {user_response}")
        
        # 根据用户回复处理
        if user_response == "中断":
            # 用户选择中断，取消整个任务
            raise asyncio.CancelledError()
        elif user_response == "修改":
            # 用户选择修改，这里可以处理修改逻辑
            # 修改完成后，可能重新询问或继续
            await self.send_message("请提供修改意见...")
            # 再次等待用户输入修改内容
            modification = await self.wait_for_user_input()
            self.context["modification"] = modification
            # 处理修改...
        elif user_response == "修改第一章":
            # 特定修改指令
            await self.handle_chapter_modification(1)
        
        # 如果是"继续"，直接返回，继续执行后面的代码
        
        return user_response
    
    async def wait_for_user_input(self) -> str:
        """等待用户输入（通用等待方法）"""
        self.pending_future = asyncio.Future()
        self.state = State.AWAITING_USER
        return await self.pending_future
    
    async def handle_user_response(self, response: str):
        """处理用户在 AWAITING_USER 状态下的回复"""
        
        if self.pending_future and not self.pending_future.done():
            # 把用户的回复设置到 Future 中
            # 这会唤醒正在 ask_user_decision 中等待的协程
            self.pending_future.set_result(response)
            self.pending_future = None
            self.state = State.EXECUTING  # 恢复为执行状态
        else:
            # 没有等待中的 Future，说明状态异常
            logger.warning(f"收到消息但没有等待中的决策: {response}")
            await self.websocket.send_json({
                "type": "error",
                "content": "当前没有等待中的决策"
            })
    
    async def handle_interrupt(self, message: str):
        """处理主动打断"""
        logger.info(f"用户主动打断: {message}")
        
        # 取消当前执行的任务
        if self.context.get("current_task"):
            self.context["current_task"].cancel()
        
        self.state = State.INTERRUPTED
        self.context["interrupt_message"] = message
        
        await self.websocket.send_json({
            "type": "interrupt",
            "content": f"已打断，您的意见: {message}，请输入'继续'恢复或发送新指令"
        })
    
    async def resume_workflow(self):
        """恢复被打断的工作流"""
        self.state = State.EXECUTING
        # 可以重新开始或从断点继续
        await self.websocket.send_json({
            "type": "status",
            "content": "恢复执行..."
        })
        # 重新创建执行任务
        self.context["current_task"] = asyncio.create_task(
            self.execute_workflow()
        )
    
    async def handle_chapter_modification(self, chapter: int):
        """处理章节修改"""
        await self.send_message(f"正在修改第{chapter}章...")
        # 修改逻辑...
        await asyncio.sleep(1)
        await self.send_message(f"第{chapter}章修改完成")
    
    async def send_message(self, content: str, msg_type: str = "info"):
        """发送消息给客户端"""
        await self.websocket.send_json({
            "type": msg_type,
            "content": content
        })

# WebSocket 服务器
async def websocket_handler(websocket, path):
    """处理 WebSocket 连接"""
    workflow = AgentWorkflow(websocket)
    
    try:
        async for message in websocket:
            data = json.loads(message)
            content = data.get("content", "")
            
            # 所有消息都交给 workflow 处理
            await workflow.process_message(content)
            
    except websockets.exceptions.ConnectionClosed:
        logger.info("连接关闭")
    except Exception as e:
        logger.error(f"错误: {e}")

async def main():
    """启动服务器"""
    async with websockets.serve(websocket_handler, "localhost", 8765):
        logger.info("WebSocket 服务器运行在 ws://localhost:8765")
        await asyncio.Future()  # 永久运行

if __name__ == "__main__":
    asyncio.run(main())


# 主动打断 vs 等待决策
# 1. 主动打断（不需要 Future）
# 主动打断的场景
# 用户正在看AI自动写作，突然说："停下！"

# # 处理逻辑：
# 1. 收到新消息 "停下"
# 2. 直接取消当前正在运行的 task
# 3. 不需要 Future，因为不需要等待回复

# 2. 等待决策（需要 Future）
# 等待决策的场景
# AI写到一半，主动问用户："大纲已生成，是否继续？"

# # 处理逻辑：
# 1. AI主动暂停自己
# 2. 创建 Future，等待用户回复
# 3. 用户回复后，Future.set_result() 唤醒AI
# 4. AI根据回复继续执行

# 对比图
# 主动打断（无 Future）:
# 用户发送"停下" ──► 直接取消当前任务 ──► 结束

# 等待决策（有 Future）:
# AI: "继续吗？" ──► 创建 Future ──► await future (暂停)
#                                     ↑
# 用户回复"继续" ─────────────────────┘
#                                     ↓
# AI 被唤醒，继续执行

