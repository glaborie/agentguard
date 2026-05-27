from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: Annotated[str, Field(min_length=1)]


class ChatRequest(BaseModel):
    model: str = "agentguard-rag"
    messages: Annotated[list[Message], Field(min_length=1)]
    stream: bool = False
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] | None = None
    max_tokens: Annotated[int, Field(gt=0)] | None = None
    # injected by Open WebUI Langfuse Session Linker filter (v0.2+)
    chat_id: Annotated[str, Field(min_length=1)] | None = None
    message_id: Annotated[str, Field(min_length=1)] | None = None
    user_id: Annotated[str, Field(min_length=1)] | None = None
    user_name: Annotated[str, Field(min_length=1)] | None = None
