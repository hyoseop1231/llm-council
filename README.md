# LLM Council

LLM Council is a multi-turn chat application that orchestrates a "council" of various LLM models to provide comprehensive answers. It features a 3-stage deliberation process:
1.  **Stage 1**: Individual responses from multiple models (OpenAI, Anthropic, Google, xAI).
2.  **Stage 2**: Peer review and ranking where models evaluate each other's responses.
3.  **Stage 3**: A Chairman model synthesizes the best insights into a final answer.

## Features

*   **Multi-Model Council**: Leverages GPT-5.1, Claude Opus 4.5, Gemini 3 Pro, and Grok 4.
*   **3-Stage Deliberation**: Ensures high-quality, verified, and synthesized responses.
*   **Multimodal Support**: Upload images, PDFs, and text files for analysis.
*   **Conversation Management**: Save, delete, and export conversations.
*   **Streaming Responses**: Real-time feedback on each stage of the process.

## Tech Stack

*   **Backend**: Python, FastAPI, Uvicorn
*   **Frontend**: React, Vite
*   **API**: OpenRouter (for accessing various LLMs)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <your-repo-url>
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

1.  **Start the Backend**:
    ```bash
    # From the root directory
    uv run uvicorn backend.main:app --reload --port 8001
    ```

2.  **Start the Frontend**:
    ```bash
    # From the frontend directory
    npm run dev
    ```

3.  Open your browser at `http://localhost:5173`.

## License

MIT
