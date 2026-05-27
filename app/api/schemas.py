from typing import Optional

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "agentguard-rag"
    messages: list[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # injected by Open WebUI Langfuse Session Linker filter (v0.2+)
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
