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
    
    async def processing(self, user_input: str = None, interrupt: bool = False):
        """处理用户的交互反馈
        纯管道：组装上下文 → Agent 处理 → 流式输出
            
        """
        print(f"\n🔄 [ConversationStore.processing] 处理输入: {user_input}, interrupt={interrupt}")
        # - 第一先把历史消息加载过来 历史消息可能为空
        # - 再把用户最新的消息进行处理
        # - 根据用户和历史消息的内容， 分析用户的意图
        # - 用户的意图可能是： 1.刚开始写报告。2.基于已有的历史进行修改。3.对某个段落进行修改。4.对某个段落进行重写。5.其他
        # - 分析用户意图的时候。需要流式的分析过程返回给前端  
        # - 分析出以后 就根据用户的意图进行执行 执行的过程也需要流式的返回给前端。
        # - 每次执行完一个操作 就询问用户是否满意。用户如果满意就继续执行下一个操作。
        # - 用户如果不满意 就根据用户的反馈进行修改。 
        # - 这个过程是一个循环 直到用户确认报告完成。

        print("005...",datetime.now(timezone.utc).isoformat())
        # 如果有正在运行的，取消它
        if interrupt:
            try:
                print("🛑 用户打断了，设置取消标志")
                self._cancel_event.set()  #标志设为 True，通知正在运行的任务停止
                # 给正在运行的任务一点时间响应取消
                await asyncio.sleep(0.1)
                # 重置标志，准备新的运行
                self._cancel_event.clear()  # 标志重置为 False
                pass
            except asyncio.CancelledError:
                pass
            finally:
                assistant_content = {"role": "assistant", "content": self.full_response, "timestamp": datetime.now(timezone.utc).isoformat()}
                self.history.append(assistant_content)
                await self._save(assistant_content)  # 保存对话状态到数据库 数据库方面以后再处理        
                self.full_response= ""
                # 如果是纯打断（没有新输入），就返回
                if not user_input:
                    yield {"type": "interrupt", "message": "已中断"}
                    return
        

       # 组装上下文
        context = {
            "history": self.history[-10:],
            "interrupt": interrupt,
            "user_input": user_input
        }

        # 保存用户输入
        if user_input:
            current_content = {"role": "user", "content": user_input, "timestamp": datetime.now(timezone.utc).isoformat()}
            self.history.append(current_content)
            await self._save(current_content)  # 保存对话状态到数据库

        


        prompt = self.getPrompt(context)
       
            
        print(f"🔄 before...." * 20)
        print(prompt)
        # 等待并yield结果
        try:
            # 从任务中获取异步生成器
            async for chunk in self.agent.run([{"role": "user", "content": prompt}], stream=True):

                # 关键：每次迭代都检查是否被打断
                chunk_type = chunk.get("type", "chunk")
                print("*" * 50)
                print(chunk_type)
                if self._cancel_event.is_set():
                    print("⏹️ 检测到取消标志，提前终止生成")
                    break  # 立即停止生成
                if chunk_type == "chunk":
                    text = chunk.get("content", "")
                    self.full_response += text
                    print(text,"\n")
                    yield {"type": "chunk", "content": text}
                else:
                    # 只有在没有被取消的情况下才保存
                    print("=" * 30)
                    print(chunk_type)
                    if not self._cancel_event.is_set():
                        assistant_content = {"role": "assistant", "content": self.full_response, "timestamp": datetime.now(timezone.utc).isoformat()}
                        self.history.append(assistant_content)
                        await self._save(assistant_content)  # 保存对话状态到数据库 数据库方面以后再处理
                        self.full_response= ""

        except asyncio.CancelledError:
            print("🛑 当前处理被取消")
            # 确保任务也被取消
            yield {"type": "cancelled"}
        except Exception as e:
            print(f"处理过程中发生错误: {str(e)}")
            yield {
                    "type": "error",
                    "message": str(e)
                }
    

    
   
if __name__ == "__main__":
    import asyncio
    pass
   
        
                   