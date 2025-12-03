import { useState, useEffect, useRef } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import KnowledgeBase from './components/KnowledgeBase';
import { api } from './api';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showKnowledgeBase, setShowKnowledgeBase] = useState(false);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId && !currentConversation) { // Only load if not already loaded
      handleSelectConversation(currentConversationId);
    }
  }, [currentConversationId, currentConversation]);

  const loadConversations = async () => {
    try {
      const data = await api.listConversations();
      setConversations(Array.isArray(data) ? data : data.conversations || []);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    setIsLoading(true); // Reuse isLoading or add specific state
    try {
      const newConv = await api.createConversation();
      setConversations([
        {
          id: newConv.id,
          title: newConv.title,
          created_at: newConv.created_at,
          message_count: 0,
        },
        ...conversations || [],
      ]);
      setCurrentConversationId(newConv.id);
      setCurrentConversation(newConv);
    } catch (error) {
      console.error('Failed to create conversation:', error);
      alert(`Failed to create new conversation: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectConversation = async (id) => {
    setCurrentConversationId(id);
    setIsLoading(true);
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteConversation = async (id) => {
    try {
      await api.deleteConversation(id);
      setConversations(conversations.filter((c) => c.id !== id));
      if (currentConversationId === id) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleSendMessage = async (content, attachments = [], useRag = false) => {
    if (!currentConversationId) return;

    // Optimistic update
    const tempUserMsg = {
      role: 'user',
      content,
      attachments, // Store attachments for display
      timestamp: new Date().toISOString(),
    };

    const tempAssistantMsg = {
      role: 'assistant',
      stage1: null,
      stage2: null,
      stage3: null,
      timestamp: new Date().toISOString(),
    };

    setCurrentConversation((prev) => ({
      ...prev,
      messages: [...prev.messages, tempUserMsg, tempAssistantMsg],
    }));

    try {
      let lastMsg = tempAssistantMsg;

      await api.sendMessageStream(
        currentConversationId,
        content,
        attachments,
        useRag,
        (type, event) => {
          switch (type) {
            case 'stage1_start':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                // Ensure we are updating the last message which is the assistant's
                const lastIdx = newMessages.length - 1;
                newMessages[lastIdx] = { ...newMessages[lastIdx], stage1: { status: 'in_progress', responses: [] } };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage1_update':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                const currentStage1 = newMessages[lastIdx].stage1 || { responses: [] };

                // Check if we already have this model's response
                const existingIdx = currentStage1.responses.findIndex(r => r.model === event.model);
                let newResponses = [...currentStage1.responses];

                if (existingIdx >= 0) {
                  newResponses[existingIdx] = event;
                } else {
                  newResponses.push(event);
                }

                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage1: { ...currentStage1, status: 'in_progress', responses: newResponses }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage1_complete':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage1: { ...newMessages[lastIdx].stage1, status: 'complete', responses: event.data }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage2_start':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage2: { status: 'in_progress', rankings: [] }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage2_update':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                const currentStage2 = newMessages[lastIdx].stage2 || { rankings: [] };

                const existingIdx = currentStage2.rankings.findIndex(r => r.model === event.model);
                let newRankings = [...currentStage2.rankings];

                if (existingIdx >= 0) {
                  newRankings[existingIdx] = event;
                } else {
                  newRankings.push(event);
                }

                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage2: { ...currentStage2, status: 'in_progress', rankings: newRankings }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage2_complete':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                // event.data is the rankings array
                // event.metadata contains label_to_model and aggregate_rankings
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage2: { ...newMessages[lastIdx].stage2, status: 'complete', rankings: event.data },
                  metadata: { ...newMessages[lastIdx].metadata, ...event.metadata }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage3_start':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage3: { status: 'in_progress', response: '' }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage3_update':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                const currentStage3 = newMessages[lastIdx].stage3 || { response: '' };
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage3: { ...currentStage3, status: 'in_progress', response: currentStage3.response + event.data }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage3_complete':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                // event.data is { model: ..., response: ... }
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  stage3: { ...newMessages[lastIdx].stage3, status: 'complete', ...event.data }
                };
                return { ...prev, messages: newMessages };
              });
              // Refresh conversation list to update message count/preview
              loadConversations();
              break;
            case 'stage4_start':
              setCurrentConversation((prev) => {
                const newMessages = [...prev.messages];
                const lastIdx = newMessages.length - 1;
                newMessages[lastIdx] = {
                  ...newMessages[lastIdx],
                  loading: { ...newMessages[lastIdx].loading, stage4: true }
                };
                return { ...prev, messages: newMessages };
              });
              break;
            case 'stage4_complete': // Added from instruction
              setCurrentConversation(prev => {
                if (!prev) return prev;
                const newMessages = [...prev.messages];
                const lastMsg = newMessages[newMessages.length - 1];
                if (lastMsg.role === 'assistant') {
                  lastMsg.stage4 = event.data; // event.data is the result
                }
                return { ...prev, messages: newMessages };
              });
              break;
            case 'clarification_needed': // Added from instruction
              setCurrentConversation(prev => {
                if (!prev) return prev;
                const newMessages = [...prev.messages];
                const lastMsg = newMessages[newMessages.length - 1];
                if (lastMsg.role === 'assistant') {
                  lastMsg.isClarification = true;
                  // event is { type: '...', data: { questions: [...], reasoning: '...' } }
                  lastMsg.clarificationData = event.data; // Store full structure
                  lastMsg.content = event.data?.reasoning || 'Clarification needed'; // Fallback content
                  lastMsg.clarificationReasoning = event.data?.reasoning || '';
                  // Clear loading states
                  // lastMsg.loading = {}; 
                }
                return { ...prev, messages: newMessages };
              });
              break;
            case 'complete': // Added from instruction
              setIsLoading(false);
              break;
            case 'error':
              console.error('Stream error:', event); // event corresponds to data.message in the instruction
              setIsLoading(false); // Added from instruction
              break;
          }
        }
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
    }
  };

  return (
    <div className="app-container">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        onOpenKnowledgeBase={() => setShowKnowledgeBase(true)}
        isLoading={isLoading}
      />
      {currentConversationId ? (
        <ChatInterface
          conversation={currentConversation}
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          onUploadFile={api.uploadFile}
        />
      ) : (
        <div className="welcome-screen">
          <h1>Welcome to LLM Council</h1>
          <p>Select a conversation or start a new one.</p>
        </div>
      )}

      {showKnowledgeBase && (
        <KnowledgeBase onClose={() => setShowKnowledgeBase(false)} />
      )}
    </div>
  );
}

export default App;
