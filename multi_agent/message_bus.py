#此文件用于多智能体协同 消息中心

"""
复杂消息总线 - 支持多智能体之间的高级通信模式
功能特性：
- 发布/订阅：智能体可以订阅感兴趣的主题，当有消息发布时自动接收
- 点对点通信：直接向特定智能体发送消息
- 请求-响应模式：支持同步请求和异步响应
- 消息过期：可设置消息生存时间，自动清理
- 历史记录：可查询过往消息（按主题、发送者、时间）
- 线程安全：支持多线程并发访问
"""

import threading
import time
import uuid
from typing import Dict, List, Any, Callable, Optional, Union
from datetime import datetime, timedelta
from enum import Enum
import json
import os

class MessageType(Enum):
    """消息类型枚举"""
    PUBLISH = "publish"           # 发布消息
    DIRECT = "direct"             # 点对点消息
    REQUEST = "request"           # 请求消息
    RESPONSE = "response"         # 响应消息
    CONTROL = "control"           # 控制消息（如停止、暂停等）

class Message:
    """消息对象"""
    def __init__(self, 
                 msg_type: MessageType,
                 content: Any,
                 sender: Optional[str] = None,
                 recipient: Optional[str] = None,
                 topic: Optional[str] = None,
                 ttl: Optional[int] = None,  # 生存时间（秒），None表示永不过期
                 correlation_id: Optional[str] = None,  # 用于请求-响应关联
                 **kwargs):
        self.id = str(uuid.uuid4())
        self.timestamp = time.time()
        self.type = msg_type
        self.content = content
        self.sender = sender
        self.recipient = recipient
        self.topic = topic
        self.ttl = ttl
        self.correlation_id = correlation_id or self.id
        self.metadata = kwargs  # 其他元数据

    def is_expired(self) -> bool:
        """检查消息是否过期"""
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl

    def to_dict(self) -> dict:
        """转换为字典（用于存储或序列化）"""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.type.value,
            "content": self.content,
            "sender": self.sender,
            "recipient": self.recipient,
            "topic": self.topic,
            "ttl": self.ttl,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建消息对象"""
        return cls(
            msg_type=MessageType(data["type"]),
            content=data["content"],
            sender=data.get("sender"),
            recipient=data.get("recipient"),
            topic=data.get("topic"),
            ttl=data.get("ttl"),
            correlation_id=data.get("correlation_id"),
            **data.get("metadata", {})
        )


class Subscription:
    """订阅信息"""
    def __init__(self, topic: str, callback: Callable[[Message], None], subscriber_id: str):
        self.topic = topic
        self.callback = callback
        self.subscriber_id = subscriber_id
        self.created_at = time.time()


class MessageBus:
    """复杂消息总线"""

    def __init__(self, enable_persistence: bool = False, persistence_dir: str = "bus_history"):
        self._lock = threading.RLock()
        self._messages: Dict[str, Message] = {}  # 按消息ID存储所有消息（历史）
        self._subscriptions: Dict[str, List[Subscription]] = {}  # topic -> 订阅者列表
        self._pending_requests: Dict[str, threading.Event] = {}  # correlation_id -> Event（用于同步等待）
        self._request_responses: Dict[str, Message] = {}  # correlation_id -> 响应消息
        self._enable_persistence = enable_persistence
        self._persistence_dir = persistence_dir
        if enable_persistence:
            os.makedirs(persistence_dir, exist_ok=True)
            self._load_history()

    def _save_message(self, msg: Message):
        """持久化保存消息（可选）"""
        if not self._enable_persistence:
            return
        filepath = os.path.join(self._persistence_dir, f"{msg.id}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(msg.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[消息总线] 持久化失败: {e}")

    def _load_history(self):
        """加载历史消息（重启时恢复）"""
        if not os.path.exists(self._persistence_dir):
            return
        for filename in os.listdir(self._persistence_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(self._persistence_dir, filename), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        msg = Message.from_dict(data)
                        self._messages[msg.id] = msg
                except Exception as e:
                    print(f"[消息总线] 加载历史消息失败 {filename}: {e}")

    # ---------- 发布/订阅 ----------
    def publish(self, topic: str, content: Any, sender: Optional[str] = None, ttl: Optional[int] = None) -> str:
        """
        向指定主题发布消息，所有订阅该主题的智能体将收到回调
        返回消息ID
        """
        msg = Message(
            msg_type=MessageType.PUBLISH,
            content=content,
            sender=sender,
            topic=topic,
            ttl=ttl
        )
        with self._lock:
            self._messages[msg.id] = msg
            self._save_message(msg)
            # 通知订阅者
            if topic in self._subscriptions:
                for sub in self._subscriptions[topic][:]:  # 使用副本防止回调中修改
                    try:
                        sub.callback(msg)
                    except Exception as e:
                        print(f"[消息总线] 订阅者 {sub.subscriber_id} 回调异常: {e}")
        return msg.id

    def subscribe(self, topic: str, callback: Callable[[Message], None], subscriber_id: str):
        """
        订阅指定主题
        :param topic: 主题名称
        :param callback: 当新消息到达时调用的函数，接收一个Message参数
        :param subscriber_id: 订阅者标识（通常是智能体ID）
        """
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            sub = Subscription(topic, callback, subscriber_id)
            self._subscriptions[topic].append(sub)
            print(f"[消息总线] {subscriber_id} 订阅主题 {topic}")

    def unsubscribe(self, topic: str, subscriber_id: str):
        """取消订阅"""
        with self._lock:
            if topic in self._subscriptions:
                self._subscriptions[topic] = [s for s in self._subscriptions[topic] if s.subscriber_id != subscriber_id]
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]

    # ---------- 点对点通信 ----------
    def send(self, recipient: str, content: Any, sender: Optional[str] = None, ttl: Optional[int] = None) -> str:
        """
        向指定智能体发送点对点消息（接收者需自己处理消息）
        返回消息ID
        """
        msg = Message(
            msg_type=MessageType.DIRECT,
            content=content,
            sender=sender,
            recipient=recipient,
            ttl=ttl
        )
        with self._lock:
            self._messages[msg.id] = msg
            self._save_message(msg)
            # 注意：点对点消息需要接收者主动读取或通过回调，这里不自动触发
        return msg.id

    # ---------- 请求-响应模式 ----------
    def request(self, target_agent: str, request_content: Any, sender: Optional[str] = None,
                timeout: Optional[float] = 30.0, ttl: Optional[int] = None) -> Optional[Any]:
        """
        发送同步请求，等待响应
        :param target_agent: 目标智能体ID
        :param request_content: 请求内容
        :param sender: 发送者ID
        :param timeout: 超时时间（秒），None表示无限等待
        :param ttl: 消息生存时间
        :return: 响应内容，超时或失败返回None
        """
        correlation_id = str(uuid.uuid4())
        req_msg = Message(
            msg_type=MessageType.REQUEST,
            content=request_content,
            sender=sender,
            recipient=target_agent,
            correlation_id=correlation_id,
            ttl=ttl
        )
        event = threading.Event()
        with self._lock:
            self._messages[req_msg.id] = req_msg
            self._save_message(req_msg)
            self._pending_requests[correlation_id] = event

        # 等待响应
        event.wait(timeout=timeout)
        with self._lock:
            if correlation_id in self._request_responses:
                resp = self._request_responses.pop(correlation_id)
                self._pending_requests.pop(correlation_id, None)
                return resp.content
            else:
                self._pending_requests.pop(correlation_id, None)
                return None

    def respond(self, request_msg: Message, response_content: Any):
        """
        响应请求（由目标智能体调用）
        :param request_msg: 接收到的请求消息
        :param response_content: 响应内容
        """
        if request_msg.type != MessageType.REQUEST:
            raise ValueError("不是请求消息")
        resp_msg = Message(
            msg_type=MessageType.RESPONSE,
            content=response_content,
            sender=request_msg.recipient,  # 响应的发送者是原接收者
            recipient=request_msg.sender,
            correlation_id=request_msg.correlation_id
        )
        with self._lock:
            self._messages[resp_msg.id] = resp_msg
            self._save_message(resp_msg)
            # 如果有等待的请求，触发事件
            if request_msg.correlation_id in self._pending_requests:
                self._request_responses[request_msg.correlation_id] = resp_msg
                self._pending_requests[request_msg.correlation_id].set()
            # 也可以作为点对点消息发送，让发送者通过其他方式接收

    # ---------- 消息查询 ----------
    def get_message(self, msg_id: str) -> Optional[Message]:
        """根据消息ID获取消息"""
        with self._lock:
            return self._messages.get(msg_id)

    def get_history(self, topic: Optional[str] = None, sender: Optional[str] = None,
                    recipient: Optional[str] = None, msg_type: Optional[MessageType] = None,
                    since: Optional[float] = None) -> List[Message]:
        """
        查询历史消息（按条件过滤）
        :param topic: 主题
        :param sender: 发送者
        :param recipient: 接收者
        :param msg_type: 消息类型
        :param since: 起始时间戳
        :return: 消息列表（按时间倒序）
        """
        with self._lock:
            result = []
            for msg in self._messages.values():
                if msg.is_expired():
                    continue  # 过期消息不返回
                if topic and msg.topic != topic:
                    continue
                if sender and msg.sender != sender:
                    continue
                if recipient and msg.recipient != recipient:
                    continue
                if msg_type and msg.type != msg_type:
                    continue
                if since and msg.timestamp < since:
                    continue
                result.append(msg)
            result.sort(key=lambda m: m.timestamp, reverse=True)
            return result

    def clean_expired(self):
        """清理所有过期消息（从内存和持久化存储中移除）"""
        with self._lock:
            expired_ids = [msg_id for msg_id, msg in self._messages.items() if msg.is_expired()]
            for msg_id in expired_ids:
                del self._messages[msg_id]
                if self._enable_persistence:
                    try:
                        os.remove(os.path.join(self._persistence_dir, f"{msg_id}.json"))
                    except:
                        pass
            print(f"[消息总线] 清理了 {len(expired_ids)} 条过期消息")

    # ---------- 状态查询 ----------
    def get_stats(self) -> dict:
        """获取总线统计信息"""
        with self._lock:
            return {
                "total_messages": len(self._messages),
                "active_subscriptions": sum(len(subs) for subs in self._subscriptions.values()),
                "pending_requests": len(self._pending_requests)
            }


# 可选：全局单例实例（根据需求决定是否使用）
_default_bus = None

def get_default_bus():
    global _default_bus
    if _default_bus is None:
        _default_bus = MessageBus()
    return _default_bus