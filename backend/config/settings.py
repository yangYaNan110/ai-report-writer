"""
配置管理
阶段0：基础配置加载
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用配置
    APP_ENV: str = Field(default="development", env="APP_ENV")
    DEBUG: bool = Field(default=True, env="DEBUG")
    PORT: int = Field(default=8000, env="PORT")
    
    # 数据库配置
    DATABASE_URL: str = Field(
        default="sqlite:///data/conversations.db", 
        env="DATABASE_URL"
    )
    
    # Redis配置
    REDIS_URL: str = Field(
        default="redis://localhost:6379", 
        env="REDIS_URL"
    )
    
    # MCP服务配置
    MCP_SERVERS: List[dict] = Field(
        default=[
            {"name": "search", "url": "http://localhost:8001/mcp"},
            {"name": "parse", "url": "http://localhost:8002/mcp"},
            {"name": "analyze", "url": "http://localhost:8003/mcp"}
        ],
        env="MCP_SERVERS"
    )
    
    # LLM配置
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    DASHSCOPE_API_KEY: Optional[str] = Field(default=None, env="DASHSCOPE_API_KEY")
    
    # Agno配置
    AGNO_API_KEY: Optional[str] = Field(default=None, env="AGNO_API_KEY")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_database_url(self) -> str:
        """获取数据库URL（确保目录存在）"""
        if self.DATABASE_URL.startswith("sqlite:///"):
            # 确保data目录存在
            db_path = self.DATABASE_URL.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return self.DATABASE_URL

# 创建全局配置实例
settings = Settings()

# 打印配置信息（开发环境）
if settings.DEBUG:
    print("=" * 50)
    print("当前配置：")
    print(f"APP_ENV: {settings.APP_ENV}")
    print(f"DATABASE_URL: {settings.DATABASE_URL}")
    print(f"REDIS_URL: {settings.REDIS_URL}")
    print("=" * 50)