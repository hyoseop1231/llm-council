# LLM Council

LLM Council is a multi-turn chat application that orchestrates a "council" of various LLM models to provide comprehensive answers. It features a 5-stage deliberation process with web search, peer review, and infographic generation.

## Features

*   **Multi-Model Council**: Leverages GPT-5.1, Claude Opus 4.5, Gemini 3 Pro, and Grok 4.1.
*   **5-Stage Deliberation Process**:
    *   **Stage 0 (Web Search)**: Perplexity-powered selective web search for real-time information when needed.
    *   **Stage 1 (Individual Responses)**: Parallel responses from multiple council members.
    *   **Stage 2 (Peer Review)**: Anonymized peer evaluation and ranking of responses.
    *   **Stage 3 (Synthesis)**: Chairman model synthesizes the best insights into a final answer.
    *   **Stage 4 (Infographic)**: Auto-generated visual infographic summarizing the answer.
*   **Smart Search**: LLM-judged selective web search - only searches when real-time information is needed.
*   **Multimodal Support**: Upload images, PDFs, and text files for analysis.
*   **Prompt Optimization**: Built-in text compression and optimization to reduce token usage.
*   **Conversation Management**: Save, delete, and export conversations as JSON.
*   **Streaming Responses**: Real-time feedback on each stage of the process.
*   **Korean Language Support**: All outputs including search results and infographics in Korean.

## Architecture

```
User Query
    ↓
Stage 0: Web Search (Perplexity) - if needed
    ↓
Stage 1: Parallel queries to council models
    ↓
Stage 2: Anonymized peer ranking
    ↓
Stage 3: Chairman synthesis
    ↓
Stage 4: Infographic generation (Gemini 3 Pro Image)
    ↓
Final Response
```

## Tech Stack

*   **Backend**: Python, FastAPI, Uvicorn, httpx
*   **Frontend**: React, Vite, ReactMarkdown
*   **API**: OpenRouter (unified access to various LLMs)
*   **Models**:
    *   Council: GPT-5.1, Claude Opus 4.5, Gemini 3 Pro, Grok 4.1
    *   Chairman: Gemini 3 Pro
    *   Search: Perplexity Sonar Pro
    *   Utility: Gemini 2.5 Flash Lite
    *   Image: Gemini 3 Pro Image (Nano Banana Pro)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/llm-council.git
    cd llm-council
    ```

2.  **Backend Setup**:
    ```bash
    # Install uv (if not installed)
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Install dependencies
    uv sync

    # Create .env file
    echo "OPENROUTER_API_KEY=your_api_key_here" > backend/.env
    ```

3.  **Frontend Setup**:
    ```bash
    cd frontend
    npm install
    ```

## Usage

### Quick Start
```bash
./start.sh
```

### Manual Start

1.  **Start the Backend**:
    ```bash
    uv run uvicorn backend.main:app --reload --port 8001
    ```

2.  **Start the Frontend**:
    ```bash
    cd frontend
    npm run dev
    ```

3.  Open your browser at `http://localhost:5173`.

## Configuration

Models can be configured in `backend/config.py`:

```python
COUNCIL_MODELS = [
    "google/gemini-3-pro-preview",
    "openai/gpt-5.1",
    "anthropic/claude-opus-4.5",
    "x-ai/grok-4.1-fast:free",
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
SEARCH_MODEL = "perplexity/sonar-pro-search"
UTILITY_MODEL = "google/gemini-2.5-flash-lite"
IMAGE_MODEL = "google/gemini-3-pro-image-preview"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/conversations` | GET | List all conversations |
| `/api/conversations` | POST | Create new conversation |
| `/api/conversations/{id}` | GET | Get conversation details |
| `/api/conversations/{id}` | DELETE | Delete conversation |
| `/api/conversations/{id}/message` | POST | Send message (batch) |
| `/api/conversations/{id}/message/stream` | POST | Send message (streaming) |
| `/api/upload` | POST | Upload file attachment |

## License

MIT
