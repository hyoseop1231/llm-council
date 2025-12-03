/**
 * API client for the LLM Council backend.
 */

const API_BASE = `http://${window.location.hostname}:8001`;

export const api = {
  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`,
      {
        method: 'DELETE',
      }
    );
    if (!response.ok) {
      throw new Error('Failed to delete conversation');
    }
    return response.json();
  },

  /**
   * List repositories in Knowledge Base.
   */
  async listRepositories() {
    const response = await fetch(`${API_BASE}/api/knowledge/repositories`);
    if (!response.ok) throw new Error('Failed to list repositories');
    return response.json();
  },

  /**
   * Create a new repository in Knowledge Base.
   */
  async createRepository(name) {
    const response = await fetch(`${API_BASE}/api/knowledge/repositories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) throw new Error('Failed to create repository');
    return response.json();
  },

  /**
   * Delete a repository from Knowledge Base.
   */
  async deleteRepository(name) {
    const response = await fetch(`${API_BASE}/api/knowledge/repositories/${name}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete repository');
    return response.json();
  },

  /**
   * Upload a file to Knowledge Base.
   */
  async uploadKnowledge(file, repository = 'default') {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('repository', repository);

    const response = await fetch(`${API_BASE}/api/knowledge/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error('Failed to upload to knowledge base');
    }
    return response.json();
  },

  /**
   * List files in Knowledge Base.
   */
  async listKnowledgeFiles(repository = null) {
    const url = repository
      ? `${API_BASE}/api/knowledge/files?repository=${repository}`
      : `${API_BASE}/api/knowledge/files`;

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Failed to list knowledge files');
    }
    return response.json();
  },

  /**
   * Delete file from Knowledge Base.
   */
  async deleteKnowledgeFile(filename, repository = 'default') {
    const response = await fetch(`${API_BASE}/api/knowledge/files/${filename}?repository=${repository}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error('Failed to delete knowledge file');
    }
    return response.json();
  },

  /**
   * Upload a file.
   */
  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/api/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error('Failed to upload file');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   */
  async sendMessage(conversationId, content, attachments = []) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content, attachments }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId - The conversation ID
   * @param {string} content - The message content
   * @param {Array} attachments - List of attachments
   * @param {boolean} useRag - Whether to use RAG
   * @param {function} onEvent - Callback function for each event: (eventType, data) => void
   * @returns {Promise<void>}
   */
  async sendMessageStream(conversationId, content, attachments = [], useRag = false, onEvent) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content, attachments, use_rag: useRag }),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');

      // Keep incomplete line in buffer
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          try {
            const event = JSON.parse(data);
            onEvent(event.type, event);
          } catch (e) {
            console.error('Failed to parse SSE event:', e, data);
          }
        }
      }
    }

    // Process any remaining data in buffer
    if (buffer.startsWith('data: ')) {
      try {
        const event = JSON.parse(buffer.slice(6));
        onEvent(event.type, event);
      } catch (e) {
        // Ignore incomplete final chunk
      }
    }
  },
};
