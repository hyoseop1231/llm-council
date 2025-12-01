"""File upload handling."""

import os
import shutil
import uuid
from pathlib import Path
from fastapi import UploadFile
from typing import Dict, Any

UPLOAD_DIR = "data/uploads"

def ensure_upload_dir():
    """Ensure the upload directory exists."""
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

async def save_upload(file: UploadFile) -> Dict[str, Any]:
    """
    Save an uploaded file.

    Args:
        file: The uploaded file

    Returns:
        Dict with file info (id, filename, content_type, path)
    """
    ensure_upload_dir()
    
    file_id = str(uuid.uuid4())
    # Keep original extension
    ext = Path(file.filename).suffix
    filename = f"{file_id}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {
        "id": file_id,
        "original_filename": file.filename,
        "filename": filename,
        "content_type": file.content_type,
        "path": path
    }

def get_upload_path(filename: str) -> str:
    """Get the absolute path of an uploaded file."""
    return os.path.abspath(os.path.join(UPLOAD_DIR, filename))
