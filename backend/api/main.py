"""
AI报告写作系统 - 主应用入口
阶段0：基础FastAPI应用，带数据库支持
阶段1.2：添加WebSocket支持
"""
from fastapi.staticfiles import StaticFiles #添加静态文件服务
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from loguru import logger

from store.database import db, init_db, get_db
from config.settings import settings
from api.controllers import websocket_controller  # 导入WebSocket控制器（阶段1.2）

#配置日志   
logger.add("logs/app.log", rotation="500 MB", retention="10 days")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    - 启动时：连接数据库、初始化表
    - 关闭时：关闭数据库连接
    """
    logger.info("🚀 应用启动中...")
    # 启动时
    await db.connect()
    await init_db()
    logger.info("✅ 数据库就绪")
    
    yield
    
    # 关闭时
    logger.info("👋 应用关闭中...")
    await db.close()
    logger.info("✅ 数据库连接已关闭")

# 创建FastAPI应用
app = FastAPI(
    title="AI Report Writing System",
    description="AI驱动的交互式报告写作系统",
    version="0.1.0",
    lifespan=lifespan  # 添加生命周期管理
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(websocket_controller.router)  # 注册WebSocket控制器

# 在创建app后添加静态文件路由
# 创建static目录（如果不存在）
os.makedirs("static", exist_ok=True)
# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """健康检查接口"""
    return {
        "service": "AI Report Writing System",
        "status": "running",
        "version": "0.1.0",
        "database": "sqlite",
        "websocket": "ws://localhost:8000/ws/{client_id}"
    }

@app.get("/health")
async def health_check(db_session = Depends(get_db)):
    """健康检查接口（带数据库检查）"""
    try:
        # 简单查询测试数据库
        result = await db.fetch_one("SELECT 1 as test")
        db_ok = result is not None

        # 检查agent是否可用
        agent_ok = settings.DASHSCOPE_API_KEY is not None
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        db_ok = False
        agent_ok = False
    
    return {
        "status": "healthy" if db_ok and agent_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "agent": "configured" if agent_ok else "missing_api_key",
        "active_websockets": len(websocket_controller.active_connections)
    }

@app.get("/db-test")
async def test_database():
    """测试数据库操作（开发用）"""
    # from store.helpers import ConversationStore
    from store.conversation_store import ConversationStore
    import uuid
    
    store = ConversationStore()
    thread_id = f"test_{uuid.uuid4().hex[:8]}"
    
    # 创建
    initial_state = {
        "thread_id": thread_id,
        "title": "测试对话",
        "phase": "planning",
        "sections": []
    }
    
    await store.create(thread_id, "测试对话", initial_state)
    
    # 查询
    state = await store.load(thread_id)
    
    # 更新
    state["phase"] = "writing"
    await store.save(thread_id, state)
    
    # 列表
    conversations = await store.list(limit=5)
    
    return {
        "created": thread_id,
        "loaded_state": state,
        "recent_conversations": conversations
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG  # 开发模式自动重启
    )