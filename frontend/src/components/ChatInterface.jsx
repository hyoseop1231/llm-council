import { useState, useEffect, useRef } from 'react';
import Markdown from './Markdown';
import Stage0 from './Stage0';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import Stage4 from './Stage4';
import { api } from '../api';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
  onUploadFile,
}) {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [useRag, setUseRag] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const [expandedStages, setExpandedStages] = useState({});
  const [clarificationSelections, setClarificationSelections] = useState({}); // { msgIndex: { questionIndex: optionText } }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };


  // Autocomplete state
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [availableItems, setAvailableItems] = useState([]); // Repos + Files
  const [cursorPos, setCursorPos] = useState(0);

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  // Fetch available items for autocomplete
  useEffect(() => {
    const fetchItems = async () => {
      console.log("Fetching autocomplete items...");
      let repos = [];
      let files = [];

      try {
        const repoResponse = await api.listRepositories();
        repos = repoResponse.repositories || [];
      } catch (e) {
        console.error("Failed to list repositories:", e);
        // Fallback with debug info
        repos = ["default", `Error: ${e.message}`];
      }

      try {
        const filesResponse = await api.listKnowledgeFiles();
        files = filesResponse.files || [];
      } catch (e) {
        console.error("Failed to list files:", e);
      }

      console.log("Fetched repos:", repos);
      console.log("Fetched files:", files);

      // Combine into a single list with types
      const items = [
        ...repos.map(r => ({ type: 'repo', name: r })),
        ...files.map(f => ({ type: 'file', name: f }))
      ];
      setAvailableItems(items);
      console.log("Available items set:", items);
    };

    fetchItems();
  }, []);

  const toggleStage = (msgIndex, stageName) => {
    setExpandedStages(prev => ({
      ...prev,
      [`${msgIndex}-${stageName}`]: !prev[`${msgIndex}-${stageName}`]
    }));
  };

  const handleInputChange = (e) => {
    const text = e.target.value;
    setInput(text);

    const cursor = e.target.selectionStart;
    setCursorPos(cursor);

    // Check for @ trigger
    // Look backwards from cursor to find the last @
    const textBeforeCursor = text.slice(0, cursor);
    const lastAt = textBeforeCursor.lastIndexOf('@');

    if (lastAt !== -1) {
      // Check if there's a space before @ (or it's start of line)
      const charBeforeAt = lastAt > 0 ? textBeforeCursor[lastAt - 1] : ' ';

      if (charBeforeAt === ' ' || charBeforeAt === '\n') {
        const query = textBeforeCursor.slice(lastAt + 1);
        // If query contains space, stop suggesting (unless we want to support spaces in names, which we do)
        // But usually autocomplete stops after a space unless it's a known multi-word token.
        // Let's allow spaces for now but maybe limit length or check if it matches start of any item.

        // Filter items
        const matches = availableItems.filter(item =>
          item.name.toLowerCase().includes(query.toLowerCase())
        );

        if (matches.length > 0) {
          setSuggestions(matches);
          setShowSuggestions(true);
          setSuggestionIndex(0);
          return;
        }
      }
    }

    setShowSuggestions(false);
  };

  const handleSuggestionClick = (item) => {
    // Insert item name at cursor
    const textBeforeCursor = input.slice(0, cursorPos);
    const lastAt = textBeforeCursor.lastIndexOf('@');

    if (lastAt !== -1) {
      const prefix = input.slice(0, lastAt);
      const suffix = input.slice(cursorPos);
      const newText = `${prefix}@${item.name} ${suffix}`;
      setInput(newText);
      setShowSuggestions(false);

      // Refocus input (optional, might need ref)
    }
  };

  const handleKeyDown = (e) => {
    if (showSuggestions) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSuggestionIndex(prev => (prev + 1) % suggestions.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSuggestionIndex(prev => (prev - 1 + suggestions.length) % suggestions.length);
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        handleSuggestionClick(suggestions[suggestionIndex]);
      } else if (e.key === 'Escape') {
        setShowSuggestions(false);
      }
    } else {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    }
  };

  const handleOptionSelect = (msgIndex, questionIndex, option) => {
    setClarificationSelections(prev => {
      const msgSelections = prev[msgIndex] || {};
      const current = msgSelections[questionIndex] || [];

      // Ensure current is an array
      const currentArray = Array.isArray(current) ? current : [current];

      let newArray;
      if (currentArray.includes(option)) {
        newArray = currentArray.filter(item => item !== option);
      } else {
        newArray = [...currentArray, option];
      }

      const newMsgSelections = { ...msgSelections };
      if (newArray.length === 0) {
        delete newMsgSelections[questionIndex];
      } else {
        newMsgSelections[questionIndex] = newArray;
      }

      return {
        ...prev,
        [msgIndex]: newMsgSelections
      };
    });
  };

  const handleTextChange = (msgIndex, questionIndex, text) => {
    setClarificationSelections(prev => {
      const msgSelections = prev[msgIndex] || {};
      return {
        ...prev,
        [msgIndex]: {
          ...msgSelections,
          [questionIndex]: text // Store as string directly
        }
      };
    });
  };

  const handleSubmitClarification = (msgIndex, questions) => {
    const selections = clarificationSelections[msgIndex];
    if (!selections) return;

    // Construct the response
    // Format: 
    // Q: [Question Text]
    // A: [Selected Option1, Selected Option2]

    let responseText = "";
    questions.forEach((q, idx) => {
      const answer = selections[idx];
      if (answer) {
        const answerText = Array.isArray(answer) ? answer.join(", ") : answer;
        responseText += `Q: ${q.text}\nA: ${answerText}\n\n`;
      }
    });

    if (!responseText.trim()) return;

    onSendMessage(responseText.trim(), [], useRag);



    // Do NOT clear selections so they remain visible
    // But we might want to mark it as submitted to disable the button
    setClarificationSelections(prev => ({
      ...prev,
      [`${msgIndex}-submitted`]: true // Mark as submitted
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if ((input.trim() || attachments.length > 0) && !isLoading && !isUploading) {
      onSendMessage(input, attachments, useRag);
      setInput('');
      setAttachments([]);
    }
  };



  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    setIsUploading(true);
    try {
      const newAttachments = [];
      for (const file of files) {
        const result = await onUploadFile(file);
        newAttachments.push(result);
      }
      setAttachments(prev => [...prev, ...newAttachments]);
    } catch (error) {
      console.error("Upload failed", error);
      alert("Failed to upload file");
    } finally {
      setIsUploading(false);
      // Reset input
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removeAttachment = (index) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  };

  const handleExport = () => {
    if (!conversation) return;

    const dataStr = JSON.stringify(conversation, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `conversation-${conversation.id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  const ProgressStepper = ({ msg }) => {
    // Determine current step
    // Steps: 1: Council (Stage 1), 2: Ranking (Stage 2), 3: Synthesis (Stage 3), 4: Infographic (Stage 4)
    // We check loading states or existence of stage data

    let currentStep = 0;
    if (msg.stage4) currentStep = 4;
    else if (msg.stage3) currentStep = 3;
    else if (msg.stage2) currentStep = 2;
    else if (msg.stage1) currentStep = 1;
    else if (msg.stage0) currentStep = 0; // Search

    // If loading specific stage, that is the active step
    if (msg.loading?.stage4) currentStep = 4;
    else if (msg.loading?.stage3) currentStep = 3;
    else if (msg.loading?.stage2) currentStep = 2;
    else if (msg.loading?.stage1) currentStep = 1;
    else if (msg.loading?.stage0) currentStep = 0;

    const steps = [
      { id: 1, label: 'Council' },
      { id: 2, label: 'Ranking' },
      { id: 3, label: 'Synthesis' },
      { id: 4, label: 'Infographic' },
    ];

    return (
      <div className="progress-stepper">
        {steps.map((step, idx) => (
          <div key={step.id} className={`step-item ${currentStep >= step.id ? 'active' : ''} ${currentStep === step.id && (msg.loading?.[`stage${step.id}`] || msg.stage1?.status === 'in_progress' || msg.stage2?.status === 'in_progress' || msg.stage3?.status === 'in_progress') ? 'processing' : ''}`}>
            <div className="step-circle">{step.id}</div>
            <div className="step-label">{step.label}</div>
            {idx < steps.length - 1 && <div className="step-line"></div>}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          <>
            <div className="chat-header-actions">
              <button className="export-btn" onClick={handleExport} title="Export as JSON">
                Export
              </button>
            </div>
            {conversation.messages.map((msg, index) => (
              <div key={index} className="message-group">
                {msg.role === 'user' ? (
                  <div className="user-message">
                    <div className="message-label">You</div>
                    <div className="message-content">
                      <Markdown>{msg.content}</Markdown>
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="message-attachments">
                          {msg.attachments.map((att, i) => (
                            <div key={i} className="attachment-item">
                              {att.content_type.startsWith('image/') ? (
                                <img src={`http://localhost:8001/uploads/${att.filename}`} alt={att.original_filename} className="attachment-preview-image" />
                              ) : (
                                <div className="attachment-file-icon">📄 {att.original_filename}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="assistant-message">
                    <div className="message-label">LLM Council</div>

                    {/* Clarification Request */}
                    {msg.isClarification && (
                      <div className="clarification-container">
                        <div className="clarification-header">
                          <span className="clarification-icon">❓</span>
                          <span className="clarification-title">확인 필요 (Clarification Needed)</span>
                        </div>
                        <div className="clarification-content">
                          {msg.clarificationReasoning && (
                            <div className="clarification-reasoning">
                              <strong>이유:</strong> {msg.clarificationReasoning}
                            </div>
                          )}

                          {msg.clarificationData?.questions?.map((q, qIdx) => {
                            const currentSelection = clarificationSelections[index]?.[qIdx] || [];

                            return (
                              <div key={qIdx} className="clarification-question-group">
                                <p className="clarification-question-text">{q.text}</p>
                                {q.options && q.options.length > 0 ? (
                                  <div className="clarification-options">
                                    {q.options.map((opt, optIdx) => {
                                      const isSelected = Array.isArray(currentSelection)
                                        ? currentSelection.includes(opt)
                                        : currentSelection === opt;

                                      return (
                                        <button
                                          key={optIdx}
                                          className={`clarification-option-btn ${isSelected ? 'selected' : ''}`}
                                          onClick={() => handleOptionSelect(index, qIdx, opt)}
                                          disabled={isLoading || clarificationSelections[`${index}-submitted`]}
                                        >
                                          {opt}
                                        </button>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <div className="clarification-text-input">
                                    <textarea
                                      className="clarification-textarea"
                                      placeholder="답변을 입력해주세요..."
                                      value={currentSelection || ''}
                                      onChange={(e) => handleTextChange(index, qIdx, e.target.value)}
                                      disabled={isLoading || clarificationSelections[`${index}-submitted`]}
                                      rows={3}
                                    />
                                  </div>
                                )}
                              </div>
                            );
                          })}

                          {/* Submit Button for Clarification */}
                          {msg.clarificationData?.questions && (
                            <div className="clarification-actions">
                              {clarificationSelections[`${index}-submitted`] ? (
                                <div className="clarification-submitted-msg">
                                  ✅ 답변이 제출되었습니다. (Submitted)
                                </div>
                              ) : (
                                <button
                                  className="clarification-submit-btn"
                                  onClick={() => handleSubmitClarification(index, msg.clarificationData.questions)}
                                  disabled={isLoading || !clarificationSelections[index] || Object.keys(clarificationSelections[index]).length === 0}
                                >
                                  답변 제출 (Submit Answers)
                                </button>
                              )}
                            </div>
                          )}

                          {/* Fallback if no structured data */}
                          {!msg.clarificationData?.questions && (
                            <Markdown>{msg.content}</Markdown>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Stage 0 - Web Search */}
                    {!msg.isClarification && msg.loading?.stage0 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Checking if web search is needed...</span>
                      </div>
                    )}
                    {!msg.isClarification && msg.stage0 && <Stage0 searchResult={msg.stage0} />}

                    {/* Stage 1 */}
                    {!msg.isClarification && msg.loading?.stage1 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 1: Collecting individual responses...</span>
                      </div>
                    )}
                    {!msg.isClarification && msg.stage1 && (
                      <Stage1
                        responses={Array.isArray(msg.stage1) ? msg.stage1 : (msg.stage1.responses || [])}
                      />
                    )}

                    {/* Stage 2 */}
                    {!msg.isClarification && msg.loading?.stage2 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 2: Peer rankings...</span>
                      </div>
                    )}
                    {!msg.isClarification && msg.stage2 && (
                      <Stage2
                        rankings={Array.isArray(msg.stage2) ? msg.stage2 : (msg.stage2.rankings || [])}
                        labelToModel={msg.metadata?.label_to_model}
                        aggregateRankings={msg.metadata?.aggregate_rankings}
                      />
                    )}

                    {/* Stage 3 */}
                    {!msg.isClarification && msg.loading?.stage3 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 3: Final synthesis...</span>
                      </div>
                    )}
                    {!msg.isClarification && msg.stage3 && <Stage3 finalResponse={msg.stage3} />}

                    {/* Stage 4 - Infographic */}
                    {!msg.isClarification && msg.loading?.stage4 && (
                      <div className="stage-loading">
                        <div className="spinner"></div>
                        <span>Running Stage 4: Generating infographic...</span>
                      </div>
                    )}
                    {!msg.isClarification && msg.stage4 && <Stage4 infographicResult={msg.stage4} />}

                    {/* Progress Indicator - Moved to bottom */}
                    {!msg.isClarification && (msg.loading || msg.stage1) && (
                      <ProgressStepper msg={msg} />
                    )}
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="input-form" onSubmit={handleSubmit}>
        <div className="input-container">
          {attachments.length > 0 && (
            <div className="attachments-preview">
              {attachments.map((att, i) => (
                <div key={i} className="attachment-preview-item">
                  <span className="attachment-name">{att.original_filename}</span>
                  <button type="button" className="remove-attachment" onClick={() => removeAttachment(i)}>×</button>
                </div>
              ))}
            </div>
          )}
          <div className="input-row">
            <button
              type="button"
              className="attach-button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading || isUploading}
            >
              📎
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              style={{ display: 'none' }}
              multiple
            />
            <div className="input-wrapper">
              {showSuggestions && (
                <div className="suggestions-list">
                  {suggestions.map((item, idx) => (
                    <div
                      key={idx}
                      className={`suggestion-item ${idx === suggestionIndex ? 'active' : ''}`}
                      onClick={() => handleSuggestionClick(item)}
                    >
                      <span className="suggestion-type">{item.type === 'repo' ? '📦' : '📄'}</span>
                      <span className="suggestion-name">{item.name}</span>
                    </div>
                  ))}
                </div>
              )}
              <textarea
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Type your message... (Use @ to mention repositories or files)"
                rows={1}
                className="message-input"
              />
            </div>
            <button
              type="submit"
              className="send-button"
              disabled={isLoading || (!input.trim() && attachments.length === 0)}
            >
              Send
            </button>
          </div>
          <div className="input-options">
            <label className="rag-toggle">
              <input
                type="checkbox"
                checked={useRag}
                onChange={(e) => setUseRag(e.target.checked)}
              />
              <span>Use Knowledge Base (RAG)</span>
            </label>
          </div>
        </div>
      </form>
    </div>
  );
}
