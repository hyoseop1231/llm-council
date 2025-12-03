import json
from typing import List, Dict, Any, Optional
from . import openrouter

# Model to use for clarification (fast and smart)
CLARIFIER_MODEL = "openai/gpt-4o" 

async def assess_clarity(messages: List[Dict[str, str]], latest_user_message: str, force_followup: bool = False) -> Dict[str, Any]:
    """
    Assess if the user's intent is clear enough for a high-quality output.
    Returns a JSON object:
    {
        "sufficient": bool,
        "reasoning": str,
        "questions": str (optional, if insufficient),
        "refined_topic": str (optional, if sufficient)
    }
    """
    
    system_prompt = """You are an expert intent analyst for an LLM Council system. 
Your job is to determine if the user's latest request is specific and clear enough to be discussed by a council of LLMs (Stage 1) and then synthesized (Stage 3).

The user might ask vague questions like "Tell me about AI" or "Root industry intelligence".

If the request is VAGUE or AMBIGUOUS:
- Set "sufficient" to false.
- Provide "reasoning" on why it's vague (in Korean).
- Generate 1-2 specific, clarifying questions in "questions" to help the user narrow down their intent.
- **CRITICAL**: For each question, provide 2-4 "options" (selectable choices) that the user can click to answer easily.
- The tone should be helpful and inquisitive.
- **ALL OUTPUT MUST BE IN KOREAN.**

If the request is CLEAR and SPECIFIC (or if the conversation history clarifies it):
- Set "sufficient" to true.
- Provide "reasoning" (in Korean).
- Extract the "refined_topic" that summarizes the specific intent (in Korean).

**IMPORTANT: MULTI-TURN CLARIFICATION**
- If the user has provided answers to previous clarification questions, **EVALUATE IF THOSE ANSWERS ARE SUFFICIENT.**
- Do NOT automatically accept the first answer as sufficient.
- If the user's answer is still broad (e.g., "I want a laptop" -> "Gaming" -> still needs budget/brand?), **ASK MORE FOLLOW-UP QUESTIONS.**
- Continue asking until you have a precise, actionable topic for the Council.
- Do not be afraid to ask 2 or 3 rounds of questions if necessary.

Output MUST be a valid JSON object with this structure:
{
    "sufficient": bool,
    "reasoning": str,
    "questions": [
        {
            "text": "Question text here?",
            "options": ["Option 1", "Option 2", "Option 3"]
        }
    ],
    "refined_topic": str (optional)
}
"""

    # Inject forced follow-up instruction if needed
    if force_followup:
        system_prompt += """
\n\n**CRITICAL INSTRUCTION: FORCE FOLLOW-UP**
The system has determined that we need at least one more round of clarification to be thorough.
Even if the user's answer seems reasonably clear, **YOU MUST FIND AN ANGLE TO ASK DEEPER QUESTIONS.**
Do not set "sufficient" to true.
Find a nuance, a constraint, or a preference that hasn't been specified yet and ask about it.
**Limit yourself to 1 or 2 high-impact questions.** Do not overwhelm the user.
For example, if they said "Gaming Laptop", ask about "Screen size preference" or "Budget".
"""

    # Construct messages for the clarifier
    # We include recent history to understand context
    clarifier_messages = [{"role": "system", "content": system_prompt}]
    
    # Add last few messages for context (limit to last 5 to save tokens)
    for msg in messages[-5:]:
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, list): # Handle multimodal
            text_content = ""
            for item in content:
                if item["type"] == "text":
                    text_content += item["text"]
            content = text_content
            
        clarifier_messages.append({"role": role, "content": content})
        
    # Ensure the latest message is there (it might not be in messages list yet if called before appending)
    # The caller should pass the full history including the latest message, or we append it here if missing.
    # For now, we assume 'messages' includes the latest user prompt.
    
    try:
        # Set a shorter timeout for clarification to avoid long hangs
        response = await openrouter.query_model(CLARIFIER_MODEL, clarifier_messages, timeout=30.0)
        
        if not response:
            raise Exception("No response from clarifier model")
            
        content = response.get("content", "")
        
        # Clean up code blocks if present
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "")
        elif content.startswith("```"):
            content = content.replace("```", "")
            
        result = json.loads(content.strip())
        return result
        
    except Exception as e:
        print(f"Error in assess_clarity: {e}")
        # Fallback: assume sufficient if error, to avoid blocking
        return {
            "sufficient": True, 
            "reasoning": "Error in clarification check, proceeding.",
            "refined_topic": latest_user_message
        }
