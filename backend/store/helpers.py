# store/helpers.py
"""
【即将废弃】请使用 conversation_store.py 和 utils.py
此文件将在后续阶段删除
"""

# 为了兼容现有代码，暂时保留导入
from store.conversation_store import ConversationStore
from store.utils import json_serializer, now

__all__ = ['ConversationStore', 'json_serializer', 'now']