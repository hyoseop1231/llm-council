"""Configuration for the LLM Council."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path, override=True)

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "google/gemini-3-pro-preview",
    "openai/gpt-5.1",
    "anthropic/claude-opus-4.5",
    "x-ai/grok-4.1-fast:free",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# Search model - Perplexity for web search in Stage 0
SEARCH_MODEL = "perplexity/sonar-pro-search"

# Fast model for utility tasks (search necessity check, title generation)
UTILITY_MODEL = "google/gemini-2.5-flash-lite"

# Image generation model (Nano Banana Pro) for infographics
IMAGE_MODEL = "google/gemini-3-pro-image-preview"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
