"""
title: Langfuse Session Linker
description: Injects Open WebUI context (chat_id, message_id, user_id, user_name) into the request body so the RAG API can stamp them as Langfuse session_id, user_id, and trace metadata.
author: AgentGuard
version: 0.2.0
"""
from pydantic import BaseModel


class Filter:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    def inlet(
        self,
        body: dict,
        __metadata__: dict = {},
        __user__: dict = {},
    ) -> dict:
        if chat_id := __metadata__.get("chat_id"):
            body["chat_id"] = chat_id
        if message_id := __metadata__.get("message_id"):
            body["message_id"] = message_id
        if user_id := __user__.get("id"):
            body["user_id"] = user_id
        if user_name := __user__.get("name"):
            body["user_name"] = user_name
        return body

    def outlet(self, body: dict) -> dict:
        return body
