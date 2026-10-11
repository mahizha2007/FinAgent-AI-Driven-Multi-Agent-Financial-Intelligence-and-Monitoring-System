from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.chat_agent import ChatAgent, ChatResponse
from utils.logger import log_event


@dataclass
class ChatSessionResult:
    response: ChatResponse
    memory_snapshot: list[dict[str, Any]]


class ChatInterface:
    def __init__(self, chat_agent: ChatAgent, database_manager) -> None:
        self.chat_agent = chat_agent
        self.database_manager = database_manager

    def handle_message(self, message: str, context: dict[str, Any]) -> ChatSessionResult:
        """Handle a chatbot request with persistence and safe error handling."""
        try:
            log_event("user", "chat_input", {"message": message})
            response = self.chat_agent.respond(message, context)
            self.database_manager.log_user_query(message, response.answer)
            log_event("assistant", "chat_response", {"message": response.answer, "action": response.action_type})
            return ChatSessionResult(
                response=response,
                memory_snapshot=self.database_manager.get_recent_memory(limit=5),
            )
        except Exception as exc:
            error_response = ChatResponse(
                answer=(
                    "Insight: I could not process that request.\n\n"
                    f"Reason: {exc}\n\n"
                    "Recommendation: Please try a shorter financial question or refresh the page."
                ),
                action_type="error",
                action_payload={"error": str(exc)},
            )
            log_event("system", "chat_error", {"error": str(exc)}, level="ERROR")
            return ChatSessionResult(
                response=error_response,
                memory_snapshot=self.database_manager.get_recent_memory(limit=5),
            )
