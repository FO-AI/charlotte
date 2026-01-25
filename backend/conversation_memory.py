# EDI conversation memory management

from typing import List, Dict
from datetime import datetime


class EDIConversationMemory:
    """Manages conversation memory for EDI queries only.
    Azure AI agent handles its own thread/memory internally."""
    
    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}
    
    def get_history(self, conversation_id: str) -> List[Dict]:
        """Get conversation history for a given conversation ID"""
        return self.conversations.get(conversation_id, [])
    
    def add_message(self, conversation_id: str, role: str, content: str, metadata: Dict = None):
        """Add a message to conversation history"""
        if not conversation_id:
            return
            
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.conversations[conversation_id].append(message)
        
        # Keep only last 20 messages to prevent memory bloat
        if len(self.conversations[conversation_id]) > 20:
            self.conversations[conversation_id] = self.conversations[conversation_id][-20:]
    
    def get_context(self, conversation_id: str, max_messages: int = 5) -> str:
        """Get formatted context string from recent conversation history"""
        history = self.get_history(conversation_id)
        
        if not history:
            return ""
        
        recent = history[-max_messages:] if len(history) > max_messages else history
        
        context_parts = []
        for msg in recent:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{prefix}: {msg['content']}")
        
        if context_parts:
            return "Previous conversation:\n" + "\n".join(context_parts) + "\n\n"
        
        return ""
    
    def clear(self, conversation_id: str):
        """Clear conversation history for a given ID"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]


# Singleton instance for EDI memory
edi_memory = EDIConversationMemory()
