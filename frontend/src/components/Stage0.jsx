import Markdown from './Markdown';
import './Stage0.css';

export default function Stage0({ searchResult }) {
  if (!searchResult || !searchResult.searched) {
    return null;
  }

  const modelName = searchResult.model?.split('/').pop() || 'Search';

  return (
    <div className="stage stage0">
      <div className="stage-header">
        <h3>Stage 0: Web Search</h3>
        <span className="search-badge">Perplexity</span>
      </div>
      <div className="stage-content">
        <div className="search-result">
          <div className="search-model-label">{modelName}</div>
          <Markdown>{searchResult.response}</Markdown>
        </div>
      </div>
    </div>
  );
}
