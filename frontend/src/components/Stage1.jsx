import { useState } from 'react';
import Markdown from './Markdown';
import './Stage1.css';

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  // Debug logging
  // console.log('Stage1 responses:', responses);

  // Ensure responses is an array
  const safeResponses = Array.isArray(responses) ? responses : [];

  if (safeResponses.length === 0) {
    return null;
  }

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      <div className="tabs">
        {safeResponses.map((resp, index) => (
          <button
            key={index}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {resp.model.split('/')[1] || resp.model}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-name">{safeResponses[activeTab]?.model}</div>
        <div className="response-text">
          <Markdown>{safeResponses[activeTab]?.response}</Markdown>
        </div>
      </div>
    </div>
  );
}
