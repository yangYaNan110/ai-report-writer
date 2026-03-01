from fastapi import WebSocket
import asyncio
from typing import Optional, List, Dict, Any
from enum import Enum
from loguru import logger
from datetime import datetime,timezone


class ConversationState(Enum):
    """定义所有的聊天的状态"""
    IDLE = "idle"                    # 空闲状态
    EXECUTING = "executing"           # 执行中
    AWAITING_USER = "awaiting_user"   # 等待用户决策
    COMPLETED = "completed"           # 已完成
    INTERRUPTED = "interrupted"       # 被打断

class ConversationStore:
    '''对话类 每个对话独立实例'''

    @classmethod
    async def create(cls, thread_id: str, websocket: Optional[WebSocket] = None, agent=None) -> "ConversationStore":
        """异步工厂方法：创建实例并加载数据"""
        instance = cls(thread_id, websocket, agent)
        await instance._load_from_db()
        return instance
    
    def __init__(self, thread_id:str, websocket:WebSocket,agent=None):
        self.thread_id = thread_id
        self.websocket = websocket
        self.agent = agent
        self.history = []
        self.full_response = ""
        self.current_task : Optional[asyncio.Task] = None
        self.state = ConversationState.IDLE
        self.pending_future : Optional[asyncio.Future] = None
        self._cancel_event = asyncio.Event()  # 初始状态: False
        pass

    async def _load_from_db(self):
        """从数据库加载数据到内存"""
        print(f"\n📚 [ConversationStore._load_from_db] 开始加载对话 {self.thread_id}")
        
        # 1. 加载对话历史
        history = None
        if history:
            self.history = history 
            print(f"   ✅ 找到现有对话: {self.thread_id}")
            print(f"历史消息数量: {len(self.history)}")
            
        else:
            pass

    async def process_message(self,message:str):
        '''处理用户消息 -状态驱动的核心'''
        logger.info(f"当前状态:{self.state.value}, 收到消息:{message}")

        # 根据当前状态处理消息
        if self.state == ConversationState.IDLE or self.state == ConversationState.INTERRUPTED:
            # 空闲状态 开始新任务
            print("001...",message)
            self.state = ConversationState.EXECUTING
            await self.process(message)
        elif self.state == ConversationState.EXECUTING:
            # 执行中收到消息 -- 这里有可能主动打断
            await self.handle_interrupt(message)
        elif self.state == ConversationState.AWAITING_USER:
            # 等待用户决策-- 处理用户的回复
            await self.handle_user_response(message)
        else:
            # 已打断状态 可以重新开始或者继续
            self.state = ConversationState.EXECUTING
            await self.process(message)

        pass
   
    async def handle_interrupt(self, message:str):
        '''处理主动打断'''
        logger.info(f"用户主动打断:{message}")

        if self.current_task and not self.current_task.done():
            # 说明ai正在执行时 用户输出了新的消息 需要先取消之前的任务 并且根据用户信息决定如何处理 用户可能输出的是一些对ai的建议 
            # 也可能是停止当前ai的行为
            self._cancel_event.set()
            # 取消任务
            self.current_task.cancel()
            try:
                #  等待任务真正取消（带超时）
                await asyncio.wait_for(self.current_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # 超时或已取消，都没关系
                pass
            finally:
                self._cancel_event.clear()
                self.current_task = None



        # 第二步： 检查是否是纯打断指令 (后期可以交给ai来识别意图 开发阶段先实现功能)
        stop_words = ["停止", "中断", "停下"]
        is_pure_interrupt = any(word in message for word in stop_words)

        if is_pure_interrupt:
            await self.interupt_process()
            self.state = ConversationState.INTERRUPTED
        else:
            # 是用户的在ai回答完毕后的新问题
            self.state = ConversationState.EXECUTING
            await self.process(message)

    async def handle_user_response(self, response:str):
        '''等待用户决策-- 处理用户的回复'''
        pass
    async def resume_workflow(self):
        '''恢复被打断的工作流'''
        pass

    async def process(self, user_input:str):
        '''真正的工作流执行逻辑'''
        try:
            # ✅ 先保存用户消息到历史
            user_content = {
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            self.history.append(user_content)
            print("003...",user_content)
            await self._save(user_content)
            print("003...",user_content)

            # 获取当前输入和历史信息 交给agent进行处理
            prompt = await self._getPrompt(user_input)
            print("ai提示词:",prompt)
            self.current_task = asyncio.create_task(
                self._generate_response(prompt)
            )
            # 等待生成任务完成（或被新消息中断）
            await self.current_task
        except asyncio.CancelledError:
            # 任务被取消 这是正常的
            logger.info("任务被中断取消")
            # 发送取消通知（可选）
            await self.websocket.send_json({
                "type": "cancelled",
                "message": "生成被中断"
            })
        except Exception as e:
            pass

    async def _generate_response(self, prompt:List):
        '''agent执行过程'''
        try:
            async for chunk in self.agent.run(prompt, stream=True):
                #每次检查是否被打断
                if self._cancel_event.is_set():
                    logger.info("检测到取消标志，停止生成")
                    break
                chunk_type = chunk.get("type", "chunk")
                if chunk_type == "chunk":
                    print(chunk)
                    text = chunk.get("content", "")
                    # print(isinstance(text, str))
                    # print(text.encode('utf-8').decode('unicode-escape'))
                    # print("6666...")
                    self.full_response += text
                    
                    # 发送给前端
                    await self.websocket.send_json({
                        "type": "chunk",
                        "content": text
                    })
                    
                elif chunk_type in ["done", "complete"]:
                    # 生成完成
                    if not self._cancel_event.is_set():
                        # 保存助手回复
                        assistant_content = {
                            "role": "assistant",
                            "content": self.full_response,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        self.history.append(assistant_content)
                        await self._save(assistant_content)
                        
                        # 发送完成信号
                        # await self.websocket.send_json({
                        #     "type": "complete",
                        #     "content": self.full_response
                        # })
                        
                        self.full_response = ""
        except asyncio.CancelledError:
            # 任务被外部取消
            raise # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"生成错误: {e}")
            await self.websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        finally:
            # 清理任务引用（如果当前任务就是自己）
            if self.current_task == asyncio.current_task():
                self.current_task = None


    async def interupt_process(self):
        print("已中断当前生成...")
        if self.full_response:
            assistant_content = {"role": "assistant", "content": self.full_response, "timestamp": datetime.now(timezone.utc).isoformat()}

            self.history.append(assistant_content)
            await self._save(assistant_content)  # 保存对话状态到数据库 数据库方面以后再处理        
            self.full_response= ""

        # 改变状态
        self.state = ConversationState.INTERRUPTED
        await self.websocket.send_json({
                "type":"interrupt",
                "content": "已中断当前生成"
        })
        print("中断结束....")
        pass

    async def _getPrompt(self, user_input:str):
        '''根据当前输入以及历史信息 获取提示词
            实际项目中 看是否需要专门的agent来总结
        '''
        # 只返回历史 不修改
        return self.history.copy()

    async def _save(self,content:Dict):
        # 保存到数据库
        print("保存到数据库...")
        pass
            
        

