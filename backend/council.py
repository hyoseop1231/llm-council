"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Union, Tuple
import asyncio
import json
import re
from .openrouter import query_model, query_models_parallel
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, SEARCH_MODEL, UTILITY_MODEL, IMAGE_MODEL
from .prompt_optimizer import optimize_search_results, optimize_conversation_history, compress_text


async def check_search_necessity(user_query: str) -> bool:
    """
    Check if the user query requires web search using a fast LLM.

    Args:
        user_query: The user's question

    Returns:
        True if web search is needed, False otherwise
    """
    check_prompt = f"""Determine if this question requires real-time web search to answer properly.

Question: {user_query}

Answer YES if the question:
- Asks about recent events, news, or current information
- Asks about specific dates, prices, or statistics that change over time
- Asks about people, companies, or products that require up-to-date information
- Cannot be answered well with knowledge from 2024 or earlier

Answer NO if the question:
- Is about general knowledge, concepts, or theory
- Is about coding, math, or technical problems
- Is asking for opinions or creative content
- Can be answered with historical or stable information

Respond with ONLY "YES" or "NO", nothing else."""

    messages = [{"role": "user", "content": check_prompt}]
    response = await query_model(UTILITY_MODEL, messages, timeout=15.0)

    if response is None:
        return False  # Default to no search on failure

    answer = response.get('content', '').strip().upper()
    return answer == "YES"


async def stage0_web_search(user_query: str) -> Dict[str, Any]:
    """
    Stage 0: Perform web search using Perplexity to gather relevant information.

    Args:
        user_query: The user's question

    Returns:
        Dict with 'model', 'response', and 'searched' keys
    """
    search_prompt = f"""You are a professional research assistant. Conduct a thorough and comprehensive web search to gather all relevant information about the following question.

Question: {user_query}

Your research should include:

## 1. Core Facts & Background
- Define key terms and concepts
- Provide essential background information
- Include relevant statistics, numbers, and data points

## 2. Current State & Recent Developments
- Latest news and updates (within the past year)
- Current trends and market conditions if applicable
- Recent changes or announcements

## 3. Multiple Perspectives & Analysis
- Different viewpoints on the topic
- Expert opinions and analysis
- Pros and cons if applicable
- Controversies or debates surrounding the topic

## 4. Practical Information
- How-to guides or step-by-step processes if relevant
- Best practices and recommendations
- Common mistakes or misconceptions to avoid

## 5. Sources & References
- Cite all sources with URLs where possible
- Prioritize authoritative sources (official websites, academic papers, reputable news outlets)
- Include publication dates for time-sensitive information

Be thorough and detailed. The information you gather will be used by multiple AI models to formulate a comprehensive answer, so completeness is crucial.

IMPORTANT: Your entire response MUST be in Korean (한국어)."""

    messages = [{"role": "user", "content": search_prompt}]
    response = await query_model(SEARCH_MODEL, messages, timeout=90.0)  # Longer timeout for thorough research

    if response is None:
        return {
            "model": SEARCH_MODEL,
            "response": None,
            "searched": False,
            "optimized": False
        }

    raw_response = response.get('content', '')
    # Optimize search results to reduce tokens while preserving key information
    # Increased limit to 12000 chars for more comprehensive research
    optimized_response = optimize_search_results(raw_response, max_chars=12000)

    return {
        "model": SEARCH_MODEL,
        "response": optimized_response,
        "searched": True,
        "optimized": len(optimized_response) < len(raw_response),
        "original_length": len(raw_response),
        "optimized_length": len(optimized_response)
    }


async def stage1_collect_responses(messages: List[Dict[str, Any]], search_context: str = None) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        messages: List of message dicts (history + current query)
        search_context: Optional web search results from Stage 0

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    # If search context is provided, prepend it to the last user message
    if search_context:
        messages = messages.copy()
        # Find the last user message and enhance it with search context
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get('role') == 'user':
                original_content = messages[i].get('content', '')
                # Handle multimodal content
                if isinstance(original_content, list):
                    # Find text content and enhance it
                    enhanced_content = []
                    for item in original_content:
                        if item.get('type') == 'text':
                            enhanced_text = f"""Here is relevant information from a web search that may help answer this question:

--- Web Search Results ---
{search_context}
--- End of Search Results ---

User's Question: {item.get('text', '')}

Please use the search results above as context when formulating your response, but also apply your own knowledge and analysis."""
                            enhanced_content.append({"type": "text", "text": enhanced_text})
                        else:
                            enhanced_content.append(item)
                    messages[i] = {"role": "user", "content": enhanced_content}
                else:
                    enhanced_query = f"""Here is relevant information from a web search that may help answer this question:

--- Web Search Results ---
{search_context}
--- End of Search Results ---

User's Question: {original_content}

Please use the search results above as context when formulating your response, but also apply your own knowledge and analysis."""
                    messages[i] = {"role": "user", "content": enhanced_query}
                break

    # Query all models in parallel
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    # Format results
    stage1_results = []
    for model, response in responses.items():
        if response is not None:  # Only include successful responses
            stage1_results.append({
                "model": model,
                "response": response.get('content', '')
            })

    return stage1_results


async def stage2_collect_rankings(
    user_query: Union[str, List[Dict[str, Any]]],
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    # Extract text from user_query if it's multimodal
    query_text = user_query
    if isinstance(user_query, list):
        for item in user_query:
            if item.get("type") == "text":
                query_text = item.get("text", "")
                break

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {query_text}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually in Korean (한국어). For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your evaluation must be in Korean.
IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A는 ... (Korean evaluation)
Response B는 ... (Korean evaluation)
Response C는 ... (Korean evaluation)

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking in Korean:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from all council models in parallel
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed
            })

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: Union[str, List[Dict[str, Any]]],
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    history: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes the final answer.
    
    Args:
        user_query: Original user query (string or list for multimodal)
        stage1_results: Results from Stage 1
        stage2_results: Results from Stage 2
        history: Conversation history
        
    Returns:
        Final synthesis result
    """
    # Extract text from user_query if it's multimodal
    query_text = user_query
    if isinstance(user_query, list):
        for item in user_query:
            if item.get("type") == "text":
                query_text = item.get("text", "")
                break
    
    # Format Stage 1 responses
    stage1_text = ""
    for res in stage1_results:
        stage1_text += f"Model ({res['model']}):\n{res['response']}\n\n"
        
    # Format Stage 2 rankings
    stage2_text = ""
    for res in stage2_results:
        stage2_text += f"Reviewer ({res['model']}):\n{res['ranking']}\n\n" # Changed from 'response' to 'ranking' to match original structure
        
    chairman_prompt = f"""
You are the Chairman of the LLM Council.
Your goal is to synthesize a final, comprehensive answer to the user's query based on the initial responses from council members and their peer reviews.

User Query: {query_text}

--- Stage 1: Initial Responses ---
{stage1_text}

--- Stage 2: Peer Reviews and Rankings ---
{stage2_text}

--- Instructions ---
1. Analyze the user's query and the provided responses.
2. Identify the strengths and weaknesses pointed out in the peer reviews.
3. Synthesize a final answer that combines the best aspects of the council's responses.
4. Resolve any conflicts or disagreements between models based on facts and logic.
5. Provide a single, high-quality response in Korean (한국어) that directly answers the user.

IMPORTANT: Your final answer MUST be in Korean.
"""

    messages = []
    if history:
        messages.extend(history)
        
    messages.append({"role": "user", "content": chairman_prompt})

    # Query the chairman model
    response = await query_model(CHAIRMAN_MODEL, messages)

    if response is None:
        # Fallback if chairman fails
        return {
            "model": CHAIRMAN_MODEL,
            "response": "Error: Unable to generate final synthesis."
        }

    return {
        "model": CHAIRMAN_MODEL,
        "response": response.get('content', '')
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use a reliable model for title generation (avoid free tier rate limits)
    response = await query_model("google/gemini-2.5-flash-lite", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    history: List[Dict[str, str]] = None
) -> Tuple[Dict, List, List, Dict, Dict]:
    """
    Run the complete 4-stage council process (Stage 0-3).

    Args:
        user_query: The user's question
        history: Conversation history (list of dicts with role/content)

    Returns:
        Tuple of (stage0_result, stage1_results, stage2_results, stage3_result, metadata)
    """
    if history is None:
        history = []

    # Optimize conversation history to reduce token usage
    optimized_history = optimize_conversation_history(
        history,
        max_messages=10,
        max_chars_per_message=3000
    )

    # Ensure current query is in history
    current_messages = optimized_history.copy()
    if not current_messages or current_messages[-1].get('content') != user_query:
        current_messages.append({"role": "user", "content": user_query})

    # Stage 0: Check if web search is needed and perform if necessary
    stage0_result = {"model": SEARCH_MODEL, "response": None, "searched": False}
    search_context = None

    # Extract text from user_query for search check
    query_text = user_query
    if isinstance(user_query, list):
        for item in user_query:
            if item.get("type") == "text":
                query_text = item.get("text", "")
                break

    needs_search = await check_search_necessity(query_text)
    if needs_search:
        stage0_result = await stage0_web_search(query_text)
        if stage0_result.get("searched") and stage0_result.get("response"):
            search_context = stage0_result["response"]

    # Stage 1: Collect individual responses (with history and optional search context)
    stage1_results = await stage1_collect_responses(current_messages, search_context)

    # If no models responded successfully, return error
    if not stage1_results:
        return stage0_result, [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Synthesize final answer
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results,
        history=current_messages
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage0_result, stage1_results, stage2_results, stage3_result, metadata


async def stage4_generate_infographic(
    user_query: str,
    final_answer: str
) -> Dict[str, Any]:
    """
    Stage 4: Generate an infographic summarizing the final answer.
    Uses Nano Banana Pro (Gemini 3 Pro Image) for image generation.

    Args:
        user_query: Original user question
        final_answer: The synthesized answer from Stage 3

    Returns:
        Dict with 'model', 'image_url', and 'generated' keys
    """
    # Summarize the answer for infographic generation
    summary_for_image = compress_text(final_answer, max_chars=2000, deduplicate=True)

    infographic_prompt = f"""Create a clean, professional infographic in Korean that visually summarizes the following information.

Original Question: {user_query}

Key Information to Visualize:
{summary_for_image}

Design Requirements:
- Use a clean, modern design style
- Include clear headings and sections in Korean
- Use icons or simple graphics to represent key concepts
- Make text legible and well-organized
- Use a professional color scheme (blues, greens, or neutral tones)
- Include the main question at the top
- Organize information in a logical visual hierarchy
- Add source citations if mentioned in the content

Create an infographic image that someone could quickly scan to understand the main points."""

    messages = [{"role": "user", "content": infographic_prompt}]
    response = await query_model(IMAGE_MODEL, messages, timeout=120.0)

    if response is None:
        return {
            "model": IMAGE_MODEL,
            "image_data": None,
            "generated": False,
            "error": "Failed to generate infographic"
        }

    # Extract image from response
    # OpenRouter returns images in message.images[] array
    # Each image has: {type: "image_url", image_url: {url: "data:image/...;base64,..."}}
    image_data = None
    images = response.get('images', [])

    if images and len(images) > 0:
        first_image = images[0]
        if isinstance(first_image, dict):
            image_url_obj = first_image.get('image_url', {})
            if isinstance(image_url_obj, dict):
                image_data = image_url_obj.get('url')
            elif isinstance(image_url_obj, str):
                image_data = image_url_obj

    # Fallback: check content field
    content = response.get('content', '')
    if not image_data and content and content.startswith('data:image'):
        image_data = content

    return {
        "model": IMAGE_MODEL,
        "image_data": image_data,
        "content": content,
        "generated": image_data is not None,
        "images_count": len(images)
    }
