"""
title: Langfuse Session Linker
description: Injects the Open WebUI chat ID into the request body so the RAG API stamps it as a Langfuse session_id, grouping all turns of a conversation under one Langfuse Session.
author: AgentGuard
version: 0.1.0
"""
from pydantic import BaseModel


class Filter:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __metadata__: dict = {}) -> dict:
        chat_id = __metadata__.get("chat_id")
        if chat_id:
            body["chat_id"] = chat_id
        return body

    def outlet(self, body: dict) -> dict:
        return body
