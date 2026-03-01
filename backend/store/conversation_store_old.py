"""
对话存储类 - 每个对话一个独立实例
使用纯数据模型，包含内存缓存和业务逻辑
"""
from typing import Optional, List, Dict, Any
from datetime import datetime,timezone
import json
import asyncio
import json
from fastapi import WebSocket
from loguru import logger


class ConversationStore:
    """对话存储类 - 每个对话独立实例"""
    
    @classmethod
    async def create(cls, thread_id: str, websocket: Optional[WebSocket] = None, agent=None) -> "ConversationStore":
        """异步工厂方法：创建实例并加载数据"""
        instance = cls(thread_id, websocket, agent)
        await instance._load_from_db()
        return instance
    
    def __init__(self,  thread_id: str, websocket: Optional[WebSocket] = None, agent=None):
        self.thread_id = thread_id
        print("+" * 20)
        self.agent = agent  # 使用传入的agent实例
        self.history = []
        self.websocket = websocket  # 可选的WebSocket连接对象
        self._cancel_event = asyncio.Event()  # 初始状态: False
        self.full_response = ""
        self.current_task: Optional[asyncio.Task] = None
    
    # ==================== 私有加载和保存方法 ====================
    
    async def _load_from_db(self):
        """从数据库加载数据到内存"""
        print(f"\n📚 [ConversationStore._load_from_db] 开始加载对话 {self.thread_id}")
        
        # 1. 加载对话历史
        history = await self.getHistory()
        if history:
            self.history = history 
            print(f"   ✅ 找到现有对话: {self.thread_id}")
            print(f"历史消息数量: {len(self.history)}")
            
        else:
            pass
            
    async def getHistory(self) -> List[Dict[str, Any]]:
        """获取对话历史"""
        # 这里直接返回内存中的历史记录，实际应用中可以从数据库加载
        return None
    
    async def _save(self, new_content: Dict[str, Any]):
        """保存当前状态到数据库"""
        # print(f"\n💾 [ConversationStore._save] 保存对话 {self.thread_id}")
        # print(f"   使用连接ID: {self.db.connection_id}")  # 添加这行！
        # print(f"   连接对象ID: {id(self.db.connection)}")  # 添加这行！
        # self.conversation.updated_at = datetime.now(timezone.utc)
        # await self.db.save_conversation_info(self.thread_id, self.conversation.to_dict())
        # print(f"   ✅ 对话信息已保存")
    
   
    
   
    def getPrompt(self, context: Dict[str, Any]) -> str:
        """根据上下文生成Agent的输入提示"""
        user_input = context.get("user_input", "")
        history = context.get("history", [])
        return f"""
                历史对话：{json.dumps(history, ensure_ascii=False)}
                当前输入：{user_input}
                请处理：
                """
    
    async def processing(self, user_input: str = None):
        """处理用户的交互反馈
        纯管道：组装上下文 → Agent 处理 → 流式输出
            
        """
        try:
            print("005...",datetime.now(timezone.utc).isoformat())
            # 组装上下文
            context = {
                "history": self.history[-10:],
                "user_input": user_input
            }

            # 保存用户输入
            if user_input:
                current_content = {"role": "user", "content": user_input, "timestamp": datetime.now(timezone.utc).isoformat()}
                self.history.append(current_content)
                await self._save(current_content)  # 保存对话状态到数据库

            prompt = self.getPrompt(context)
            print(prompt, "提示词...")
            # 创建新的生成任务
            self.current_task = asyncio.create_task(
                self._generate_response(prompt)
            )

            # 等待生成任务完成（或被新消息中断）
            await self.current_task
        except asyncio.CancelledError:
            # 任务被取消，这是正常的
            logger.info("生成任务被取消")
            # 发送取消通知（可选）
            await self.websocket.send_json({
                "type": "cancelled",
                "message": "生成被中断"
            })
            
       
    async def _generate_response(self, prompt: str):
        """实际的生成逻辑（在独立任务中运行）"""
        print("008....")
        try:
            # 假设您的agent.run是异步生成器
            async for chunk in self.agent.run([{"role": "user", "content": prompt}], stream=True):
                # 每次迭代检查是否被打断
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
            logger.info("_generate_response 被取消")
            raise  # 重新抛出，让上层处理
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


    async def interrupt_current_task(self) -> bool:
        '''
        中断当前正在执行的任务
        返回: True - 成功取消了任务, False - 没有任务需要取消
        '''
        if self.current_task and not self.current_task.done():
            logger.info(f"中断当前任务:{self.current_task}")
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

            return True


        return False


    async def interupt_process(self):
        print("已中断当前生成...")
        assistant_content = {"role": "assistant", "content": self.full_response, "timestamp": datetime.now(timezone.utc).isoformat()}
        self.history.append(assistant_content)
        await self._save(assistant_content)  # 保存对话状态到数据库 数据库方面以后再处理        
        self.full_response= ""
        await self.websocket.send_json({
                "type":"interrupt",
                "content": "已中断当前生成"
        })
        print("中断结束....")

    
   
if __name__ == "__main__":
    import asyncio
    pass
   
        
                   