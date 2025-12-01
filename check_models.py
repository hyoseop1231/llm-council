#!/usr/bin/env python3
"""Check if configured models are available on OpenRouter."""

import httpx
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL, SEARCH_MODEL, UTILITY_MODEL

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def fetch_available_models():
    """Fetch list of available models from OpenRouter API."""
    try:
        response = httpx.get(OPENROUTER_MODELS_URL, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return [m["id"] for m in data.get("data", [])]
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []


def check_models():
    """Check if all configured models are available."""
    print("Fetching available models from OpenRouter...")
    available = fetch_available_models()

    if not available:
        print("Failed to fetch model list!")
        return False

    print(f"Total models available: {len(available)}")
    print("-" * 50)

    # Collect all models to check (council + chairman + search + utility)
    all_models = list(
        set(COUNCIL_MODELS + [CHAIRMAN_MODEL, SEARCH_MODEL, UTILITY_MODEL])
    )

    all_found = True
    for model in all_models:
        if model in available:
            print(f"✅ [FOUND] {model}")
        else:
            print(f"❌ [MISSING] {model}")
            all_found = False
            # Suggest closest matches
            base_name = model.split("/")[-1].split(":")[0][:8]
            closest = [m for m in available if base_name.lower() in m.lower()][:5]
            if closest:
                print(f"   Suggestions: {', '.join(closest)}")

    print("-" * 50)
    if all_found:
        print("✅ All models are available!")
    else:
        print("⚠️  Some models are missing. Update backend/config.py")

    return all_found


if __name__ == "__main__":
    success = check_models()
    sys.exit(0 if success else 1)
