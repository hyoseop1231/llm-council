"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import base64
import mimetypes
import uuid
import json
import asyncio

from . import storage
from . import uploads
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
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file."""
    return await uploads.save_upload(file)


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
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
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content)
                )

            # Get conversation history
            history = format_history_for_llm(conversation["messages"])

            # Process attachments if any
            processed_content = request.content
            if request.attachments:
                print(f"Processing {len(request.attachments)} attachments...")
                processed_content = process_attachments(
                    request.content, request.attachments
                )
                print("Attachments processed.")

            # Stage 0: Check if web search is needed
            yield f"data: {json.dumps({'type': 'stage0_start'})}\n\n"

            # Extract text for search check
            query_text = processed_content
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


def process_attachments(content: str, attachments: List[Dict[str, Any]]) -> Any:
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
