import { useState, useEffect } from 'react';
import './Sidebar.css';

export default function Sidebar({
  conversations = [],
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onOpenKnowledgeBase,
  isLoading,
}) {
  const handleDelete = (e, id) => {
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this conversation?')) {
      onDeleteConversation(id);
    }
  };
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>LLM Council</h1>
        <button className="new-chat-btn" onClick={onNewConversation} disabled={isLoading}>
          {isLoading ? 'Creating...' : '+ New Conversation'}
        </button>

        <button className="knowledge-base-btn" onClick={onOpenKnowledgeBase}>
          📚 Knowledge Base
        </button>
      </div>

      <div className="conversations-list">
        {conversations.length === 0 ? (
          <div className="no-conversations">No conversations yet</div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === currentConversationId ? 'active' : ''
                }`}
              onClick={() => onSelectConversation(conv.id)}
            >
              <div className="conversation-title">
                {conv.title || 'New Conversation'}
              </div>
              <div className="conversation-meta">
                {conv.message_count} messages
              </div>
              <button
                className="delete-btn"
                onClick={(e) => handleDelete(e, conv.id)}
                title="Delete conversation"
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
