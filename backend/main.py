"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import FastAPI, HTTPException, UploadFile, File, Body, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import base64
import mimetypes
import uuid
import json
import asyncio
from datetime import datetime

from . import storage
from . import uploads
from . import rag
from .council import (
    run_full_council,
    generate_conversation_title,
    check_search_necessity,
    stage0_web_search,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    stage4_generate_infographic,
    calculate_aggregate_rankings,
)
from .prompt_optimizer import optimize_file_content, clean_text


def format_history_for_llm(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Format conversation history for LLM consumption.
    Extracts final response from assistant messages.
    """
    formatted_history = []
    for msg in messages:
        if msg["role"] == "user":
            formatted_history.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant":
            # For assistant messages, we only care about the final synthesized response
            # which is in stage3['response']
            if "stage3" in msg and msg["stage3"] and "response" in msg["stage3"]:
                formatted_history.append(
                    {"role": "assistant", "content": msg["stage3"]["response"]}
                )
    return formatted_history


app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploads directory for static access (optional, but useful for debugging)
import os

os.makedirs("data/uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""

    content: str
    attachments: Optional[List[Dict[str, Any]]] = None
    use_rag: bool = False


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""

    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""

    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/knowledge/repositories")
async def list_repositories():
    """List all available knowledge base repositories."""
    try:
        repos = rag.list_repositories()
        return {"repositories": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/knowledge/repositories")
async def create_repository(name: str = Body(..., embed=True)):
    """Create a new knowledge base repository."""
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Repository name cannot be empty")
    
    success = rag.create_repository(name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create repository")
    return {"message": f"Repository '{name}' created successfully"}

@app.delete("/api/knowledge/repositories/{name}")
async def delete_repository(name: str):
    """Delete a knowledge base repository."""
    success = rag.delete_repository(name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete repository")
    return {"message": f"Repository '{name}' deleted successfully"}

@app.post("/api/knowledge/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    repository: str = Form("default")
):
    """Upload a file to the knowledge base."""
    try:
        print(f"Uploading file: {file.filename} to repo: {repository}")
        
        # 1. Save file to uploads directory first
        file_info = await uploads.save_upload(file)
        print(f"File saved to: {file_info['path']}")
        
        path = uploads.get_upload_path(file_info['filename'])
        
        # 2. Add to RAG knowledge base
        print("Adding to Knowledge Base...")
        success = await rag.add_document_to_kb(
            path, 
            file_info['original_filename'], 
            file_info['content_type'],
            repository=repository
        )
        print(f"Add to KB result: {success}")
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add document to knowledge base")
            
        return {"status": "success", "filename": file_info['original_filename']}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in upload_knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/knowledge/files")
async def list_knowledge_files(repository: str = "default"):
    """List files in the knowledge base."""
    files = rag.list_documents(repository=repository)
    return {"files": files}

@app.delete("/api/knowledge/files/{filename}")
async def delete_knowledge_file(filename: str, repository: str = "default"):
    """Delete a file from the knowledge base."""
    success = rag.delete_document(filename, repository=repository)
    if not success:
        raise HTTPException(status_code=404, detail="File not found in knowledge base")
    return {"status": "success"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file."""
    return await uploads.save_upload(file)


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation():
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    success = storage.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "success"}


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Get conversation history
    history = format_history_for_llm(conversation["messages"])

    # Process attachments if any
    processed_content = request.content
    if request.attachments:
        processed_content = process_attachments(request.content, request.attachments)

    # Run the 4-stage council process (Stage 0-3)
    (
        stage0_result,
        stage1_results,
        stage2_results,
        stage3_result,
        metadata,
    ) = await run_full_council(processed_content, history=history)

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id, stage1_results, stage2_results, stage3_result, stage0_result
    )

    # Return the complete response with metadata
    return {
        "stage0": stage0_result,
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: str,
    request: SendMessageRequest
):
    """
    Stream the council process:
    1. Stage 1: Individual LLM responses (Parallel)
    2. Stage 2: Peer Review & Ranking (Parallel)
    3. Stage 3: Chairman's Synthesis
    """
    # 1. Load conversation
    conversation = storage.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    async def event_generator():
        try:
            # Check if this is the first message
            is_first_message = len(conversation["messages"]) == 0

            # Process attachments if any
            processed_content = request.content
            if request.attachments:
                print(f"Processing {len(request.attachments)} attachments...")
                processed_content = await process_attachments(request.content, request.attachments)
                print("Attachments processed.")
            
            # RAG Retrieval
            rag_context = ""
            print(f"DEBUG: request.use_rag = {request.use_rag}")
            if request.use_rag:
                print("RAG enabled. Parsing mentions and querying knowledge base...")
                
                # Parse mentions (@repo, @file)
                # We use the original text content for parsing
                query_text = request.content
                parse_result = rag.parse_mentions(query_text)
                
                cleaned_query = parse_result["cleaned_query"]
                target_repos = parse_result["repositories"]
                target_files = parse_result["files"]
                
                print(f"Parsed Mentions - Query: '{cleaned_query}', Repos: {target_repos}, Files: {target_files}")
                
                # If no specific repo mentioned, search all or default?
                # rag.query_knowledge_base handles None as "search all" (or we can change it to default)
                # Let's stick to rag.py logic (search all if None, or list_repositories if None)
                
                results = rag.query_knowledge_base(
                    cleaned_query, 
                    repositories=target_repos if target_repos else None,
                    file_filters=target_files if target_files else None
                )
                
                if results:
                    print(f"\n=== RAG RETRIEVAL SUCCESS ===")
                    print(f"Query: {cleaned_query}")
                    print(f"Target Repos: {target_repos}")
                    print(f"Target Files: {target_files}")
                    print(f"Retrieved {len(results)} chunks:")
                    
                    rag_context = "\n\n--- Retrieved Context from Knowledge Base ---\n"
                    for i, res in enumerate(results):
                        snippet = res['content'][:100].replace('\n', ' ') + "..."
                        print(f"  [{i+1}] Source: {res['metadata']['source']} (Repo: {res['repository']})")
                        print(f"      Preview: {snippet}")
                        rag_context += f"Source: {res['metadata']['source']} (Repo: {res['repository']})\nContent: {res['content']}\n\n"
                    rag_context += "--- End of Context ---\n"
                    print("=============================\n")
                    
                    # Append context to processed_content
                    # Note: We are appending to the PROMPT sent to LLM, not replacing the user's message in history immediately
                    # But for simplicity in this architecture, we modify the content passed to council.
                    
                    if isinstance(processed_content, str):
                        processed_content += rag_context
                    elif isinstance(processed_content, list):
                        # Find the text part and append
                        for item in processed_content:
                            if item["type"] == "text":
                                item["text"] += rag_context
                                break
                else:
                    print("No relevant context found in knowledge base.")

            # Add user message to history
            user_message = {
                "role": "user",
                "content": request.content, # Store original content in history
                "attachments": request.attachments,
                "timestamp": datetime.now().isoformat()
            }
            conversation["messages"].append(user_message)
            storage.save_conversation(conversation)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content)
                )

            # Get conversation history
            history = format_history_for_llm(conversation["messages"])

            # --- Clarification Stage ---
            # Check if we should run clarification
            # We run it if:
            # 1. It's enabled (defaulting to True for now, or add a flag)
            # 2. It's a user message (which it is)
            # 3. We haven't already clarified this specific topic (tracked via metadata? or just stateless check)
            
            # For this implementation, we'll do a stateless check on every message unless explicitly skipped.
            # If the clarifier says "sufficient", we proceed.
            # If "insufficient", we yield the questions and STOP.
            
            enable_clarification = True # Could be passed in request
            
            if enable_clarification:
                yield f"data: {json.dumps({'type': 'clarification_start'})}\n\n"
                
                # Prepare history for clarifier
                # We need to include the current message which was just added to conversation["messages"]
                # But wait, we added it above.
                
                # Note: format_history_for_llm extracts only text.
                # clarifier.assess_clarity expects raw messages or similar.
                # Let's pass the raw conversation["messages"] to clarifier, it handles parsing.
                
                from . import clarifier
                
                # Count previous clarification rounds
                clarification_count = sum(1 for m in conversation["messages"] if m.get("is_clarification"))
                print(f"Clarification count so far: {clarification_count}")
                
                # FLEXIBLE LOGIC: Min 2, Max 4 rounds
                # 1. If we have done 4 or more rounds, we treat it as "Sufficient" to trigger the final check.
                if clarification_count >= 4:
                    print("Max clarification rounds (4) reached. Treating as sufficient.")
                    clarity_result = {"sufficient": True, "refined_topic": "Max rounds reached"}
                else:
                    # 2. If we are under 2 rounds, FORCE follow-up.
                    # 3. If we are between 2 and 4 rounds, allow follow-up but don't force it.
                    force_followup = clarification_count < 2
                    
                    print(f"Assessing clarity (Round {clarification_count + 1}, Forced: {force_followup})...")
                    clarity_result = await clarifier.assess_clarity(
                        conversation["messages"], 
                        request.content,
                        force_followup=force_followup
                    )
                
                print(f"Clarity Result: {clarity_result}")
                
                if not clarity_result.get("sufficient", True):
                    # Case: Insufficient / Ambiguous
                    # We stream the clarification questions as a "response" but with a specific type or just as text?
                    # If we just stream it as text, the frontend displays it as an assistant message.
                    # That's actually perfect. The user answers, and the loop continues.
                    
                    questions = clarity_result.get("questions", [])
                    reasoning = clarity_result.get("reasoning", "")
                    
                    # Ensure questions is a list of objects (handle legacy string list if model fails)
                    # The model should return [{"text": "...", "options": [...]}]
                    # If it returns strings, wrap them.
                    processed_questions = []
                    if isinstance(questions, list):
                        for q in questions:
                            if isinstance(q, str):
                                processed_questions.append({"text": q, "options": []})
                            elif isinstance(q, dict):
                                processed_questions.append(q)
                    
                    # We send the structured data to the frontend
                    # The frontend will render the buttons.
                    
                    # Save this interaction so the next turn includes it contextually.
                    # Save a text representation for history
                    text_rep = reasoning + "\n"
                    for q in processed_questions:
                        text_rep += f"\nQ: {q.get('text')}"
                        if q.get('options'):
                            text_rep += f" (Options: {', '.join(q['options'])})"

                    clarification_msg = {
                        "role": "assistant",
                        "content": text_rep,
                        "is_clarification": True,
                        "clarification_data": {"questions": processed_questions, "reasoning": reasoning},
                        "timestamp": datetime.now().isoformat()
                    }
                    conversation["messages"].append(clarification_msg)
                    storage.save_conversation(conversation)
                    
                    yield f"data: {json.dumps({'type': 'clarification_needed', 'data': {'questions': processed_questions, 'reasoning': reasoning}})}\n\n"
                    yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                    return # STOP here, don't run the rest of the council
                
                else:
                    # Case: Sufficient (or forced to stop by max rounds logic below)
                    print(f"Intent is clear: {clarity_result.get('refined_topic')}")
                    
                    # FINAL CHECK: Ask for any additional comments before proceeding
                    # Check if we already asked for final comments
                    last_assistant_msg = next((m for m in reversed(conversation["messages"]) if m["role"] == "assistant"), None)
                    is_final_check = last_assistant_msg and last_assistant_msg.get("is_final_clarification")
                    
                    if not is_final_check:
                        print("Intent clear, but asking for final comments...")
                        
                        final_question_text = "추가로 고려해야 할 사항이나 하실 말씀이 있나요? (없으시면 '없음'이라고 적어주세요)"
                        
                        # Save this interaction
                        final_msg = {
                            "role": "assistant",
                            "content": final_question_text,
                            "is_clarification": True,
                            "is_final_clarification": True, # Flag to mark this as the final check
                            "clarification_data": {
                                "questions": [{"text": final_question_text, "options": []}], # No options, just text input
                                "reasoning": "최종 확인 (Final Check)"
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        conversation["messages"].append(final_msg)
                        storage.save_conversation(conversation)
                        
                        yield f"data: {json.dumps({'type': 'clarification_needed', 'data': final_msg['clarification_data']})}\n\n"
                        yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                        return # STOP here
                    
                    # If we already asked, proceed to Stage 0
                    print("Final comments received (or skipped). Proceeding to Council.")
                    yield f"data: {json.dumps({'type': 'clarification_complete', 'data': clarity_result})}\n\n"
                    # Proceed to Stage 0...

            # Stage 0: Check if web search is needed
            yield f"data: {json.dumps({'type': 'stage0_start'})}\n\n"

            # Extract text for search check
            query_text = request.content # Use original request content for search check
            if isinstance(processed_content, list):
                for item in processed_content:
                    if item.get("type") == "text":
                        query_text = item.get("text", "")
                        break

            print("Checking if search is needed...")
            needs_search = await check_search_necessity(query_text)
            search_context = None
            stage0_result = {
                "model": "perplexity/sonar-pro-search",
                "response": None,
                "searched": False,
            }

            if needs_search:
                print("Search needed. Running Stage 0...")
                stage0_result = await stage0_web_search(query_text)
                if stage0_result.get("searched") and stage0_result.get("response"):
                    search_context = stage0_result["response"]
                    print("Stage 0 complete. Search results obtained.")
            else:
                print("Search not needed. Skipping Stage 0.")

            yield f"data: {json.dumps({'type': 'stage0_complete', 'data': stage0_result})}\n\n"

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"

            # Prepare messages with history for Stage 1
            current_messages = history.copy()

            # Handle multimodal content structure
            if isinstance(processed_content, list):
                current_messages.append({"role": "user", "content": processed_content})
            else:
                current_messages.append({"role": "user", "content": processed_content})

            print("Starting Stage 1...")
            stage1_results = await stage1_collect_responses(
                current_messages, search_context
            )
            print(f"Stage 1 complete. Got {len(stage1_results)} results.")
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(
                request.content, stage1_results
            )
            aggregate_rankings = calculate_aggregate_rankings(
                stage2_results, label_to_model
            )
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(
                processed_content,
                stage1_results,
                stage2_results,
                history=current_messages,
            )
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Stage 4: Generate infographic
            yield f"data: {json.dumps({'type': 'stage4_start'})}\n\n"
            stage4_result = await stage4_generate_infographic(
                request.content, stage3_result.get("response", "")
            )
            yield f"data: {json.dumps({'type': 'stage4_complete', 'data': stage4_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                stage0_result,
                stage4_result,
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def process_attachments(content: str, attachments: List[Dict[str, Any]]) -> Any:
    """
    Process attachments and return content suitable for LLM.
    - Images: Converted to base64 and added to multimodal content list.
    - Text/Other: Attempt to read as text and append to content.
    """
    multimodal_content = [{"type": "text", "text": content}]

    for attachment in attachments:
        path = uploads.get_upload_path(attachment["filename"])
        mime_type = attachment["content_type"]
        print(f"Processing attachment: {attachment['original_filename']} ({mime_type})")

        if mime_type.startswith("image/"):
            # Handle image
            try:
                with open(path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                    multimodal_content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded_string}"
                            },
                        }
                    )
            except Exception as e:
                print(f"Error processing image {path}: {e}")

        elif mime_type == "application/pdf":
            # Handle PDF file
            try:
                import pypdf

                reader = pypdf.PdfReader(path)
                pdf_text = ""
                for page in reader.pages:
                    pdf_text += page.extract_text() + "\n"

                # Optimize PDF content
                optimized_pdf = optimize_file_content(
                    pdf_text, attachment["original_filename"], max_chars=15000
                )
                multimodal_content[0]["text"] += (
                    f"\n\n--- Attached PDF: {attachment['original_filename']} ---\n{optimized_pdf}\n--- End of PDF ---"
                )
                print(
                    f"Successfully extracted and optimized PDF: {attachment['original_filename']} ({len(pdf_text)} -> {len(optimized_pdf)} chars)"
                )
            except Exception as e:
                print(f"Error processing PDF {path}: {e}")

        else:
            # Handle as text file (try to read everything else as text)
            try:
                with open(path, "r", encoding="utf-8") as text_file:
                    file_content = text_file.read()
                    # Optimize text file content
                    optimized_content = optimize_file_content(
                        file_content, attachment["original_filename"], max_chars=15000
                    )
                    multimodal_content[0]["text"] += (
                        f"\n\n--- Attached File: {attachment['original_filename']} ---\n{optimized_content}\n--- End of File ---"
                    )
                    print(
                        f"Successfully appended and optimized text file: {attachment['original_filename']} ({len(file_content)} -> {len(optimized_content)} chars)"
                    )
            except UnicodeDecodeError:
                print(
                    f"Warning: Could not decode {attachment['original_filename']} as UTF-8 text. Skipping."
                )
            except Exception as e:
                print(f"Error processing file {path}: {e}")

    # If we only have text (after appending text files), return string
    # If we have images, return list
    has_images = any(item["type"] == "image_url" for item in multimodal_content)

    if has_images:
        return multimodal_content
    else:
        return multimodal_content[0]["text"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
