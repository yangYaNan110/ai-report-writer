# store/utils.py
"""
store层内部使用的工具函数
注意：如果被其他层（api/）调用，请迁移到根目录 utils/
"""
import json
from datetime import datetime

def json_serializer(obj):
    """JSON序列化器，处理datetime等特殊类型
    用于sqlite的JSON字段存储
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def now():
    """获取当前UTC时间
    用于数据库记录创建时间、更新时间
    """
    return datetime.utcnow()