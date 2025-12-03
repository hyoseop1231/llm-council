"""RAG (Retrieval Augmented Generation) module using ChromaDB and SentenceTransformers."""

import os
import uuid
import shutil
import base64
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import pypdf
import docx
from . import openrouter
from .config import VLM_MODEL

# Configuration
CHROMA_DB_DIR = "data/chroma_db"
# Better Korean embedding model
EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"
DEFAULT_COLLECTION_NAME = "default"

# Global instances
_chroma_client = None
_embedding_model = None

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    return _chroma_client

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print("Embedding model loaded.")
    return _embedding_model

def _get_collection_by_display_name(display_name: str):
    """
    Find a collection by its display name (stored in metadata).
    Returns the collection object or None.
    """
    client = get_chroma_client()
    collections = client.list_collections()
    
    for col in collections:
        # Check metadata for display_name
        # Note: col.metadata might be None
        meta = col.metadata or {}
        if meta.get("display_name") == display_name:
            return col
        # Fallback: check if the actual name matches (for legacy/default)
        if col.name == display_name:
            return col
            
    return None

def get_collection(name: str = DEFAULT_COLLECTION_NAME):
    """
    Get a collection by its display name.
    Creates it if it doesn't exist (only for default).
    For custom repos, use create_repository.
    """
    client = get_chroma_client()
    
    # Try to find by display name
    col = _get_collection_by_display_name(name)
    if col:
        return col
        
    # If not found, and it's default, create it
    if name == DEFAULT_COLLECTION_NAME:
        return client.get_or_create_collection(name=DEFAULT_COLLECTION_NAME, metadata={"display_name": DEFAULT_COLLECTION_NAME})
        
    # If not found and not default, we should probably error or create?
    # The original behavior was get_or_create.
    # Let's maintain get_or_create behavior but with safe naming if it looks like it needs it.
    # But we can't easily know if "foo" is meant to be a display name or ID if we just create it.
    # Let's assume this function is mostly used internally.
    # If we are here, it means it doesn't exist.
    
    # If the name is safe, use it. If not, generate safe name.
    # But wait, if we generate a random name, we can't find it again by the unsafe name next time.
    # So we MUST persist the mapping.
    
    # Strategy: If it doesn't exist, create a new one with safe name and this display name.
    safe_name = f"repo_{uuid.uuid4().hex}"
    return client.create_collection(name=safe_name, metadata={"display_name": name})

def list_repositories() -> List[str]:
    """List all available repositories (display names)."""
    client = get_chroma_client()
    collections = client.list_collections()
    repos = []
    for c in collections:
        meta = c.metadata or {}
        repos.append(meta.get("display_name", c.name))
    return repos

def create_repository(name: str) -> bool:
    """Create a new repository with a display name."""
    try:
        client = get_chroma_client()
        
        # Check if already exists
        if _get_collection_by_display_name(name):
            print(f"Repository {name} already exists.")
            return False
            
        # Generate safe internal name
        safe_name = f"repo_{uuid.uuid4().hex}"
        
        client.create_collection(name=safe_name, metadata={"display_name": name})
        return True
    except Exception as e:
        print(f"Error creating repository {name}: {e}")
        return False

def delete_repository(name: str) -> bool:
    """Delete a repository by display name."""
    try:
        client = get_chroma_client()
        col = _get_collection_by_display_name(name)
        if col:
            client.delete_collection(name=col.name)
            return True
        return False
    except Exception as e:
        print(f"Error deleting repository {name}: {e}")
        return False

def parse_mentions(query: str) -> Dict[str, Any]:
    """
    Parse @mentions from the query.
    Prioritizes matching existing repository names (even with spaces).
    Returns:
        {
            "cleaned_query": str,
            "repositories": List[str],
            "files": List[str]
        }
    """
    import re
    
    repositories = []
    files = []
    
    # 1. Match against existing repositories (longest first to handle substrings)
    available_repos = list_repositories()
    # Sort by length descending to match "Data Science" before "Data"
    available_repos.sort(key=len, reverse=True)
    
    current_query = query
    
    for repo in available_repos:
        # Check for @Repo Name
        # We need to be careful not to match inside words, so look for @ prefix
        # and maybe a boundary after? But repo names might end with anything.
        # Simple approach: check if f"@{repo}" is in current_query
        target = f"@{repo}"
        if target in current_query:
            repositories.append(repo)
            # Remove from query
            current_query = current_query.replace(target, "")
            
    # 2. Parse remaining @mentions (likely files or unknown repos)
    # This regex matches @ followed by non-whitespace characters
    mentions = re.findall(r'@(\S+)', current_query)
    
    for mention in mentions:
        # Since we already extracted known repos, these are likely files
        # or typos. We'll treat them as files for filtering.
        files.append(mention)
        current_query = current_query.replace(f"@{mention}", "")
            
    # Clean up extra spaces
    cleaned_query = " ".join(current_query.split()).strip()
    
    if not cleaned_query:
        cleaned_query = query # Fallback if everything was removed
    
    return {
        "cleaned_query": cleaned_query,
        "repositories": repositories,
        "files": files
    }

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into chunks with overlap."""
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
        
    return chunks

async def generate_image_description(file_path: str) -> str:
    """Generate a detailed description for an image using a VLM."""
    try:
        with open(file_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in detail, focusing on extracting any text, data, or key visual information that would be useful for retrieval."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encoded_string}"
                        }
                    }
                ]
            }
        ]
        
        response = await openrouter.query_model(VLM_MODEL, messages)
        if response and response.get("content"):
            return response["content"]
        return ""
    except Exception as e:
        print(f"Error generating image description: {e}")
        return ""

async def read_file_content(file_path: str, content_type: str) -> str:
    """Read content from a file based on its type."""
    if content_type == 'application/pdf':
        try:
            reader = pypdf.PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"Error reading PDF {file_path}: {e}")
            return ""
            
    elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            print(f"Error reading DOCX {file_path}: {e}")
            return ""
            
    elif content_type.startswith('image/'):
        print(f"Generating description for image: {file_path}")
        description = await generate_image_description(file_path)
        if description:
            return f"--- Image Description ---\n{description}\n--- End Image Description ---"
        return ""
        
    else:
        # Assume text
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading text file {file_path}: {e}")
            return ""

async def add_document_to_kb(file_path: str, original_filename: str, content_type: str, repository: str = DEFAULT_COLLECTION_NAME) -> bool:
    """
    Process a file and add it to the knowledge base.
    """
    try:
        # 1. Read content (now async)
        content = await read_file_content(file_path, content_type)
        if not content.strip():
            print(f"No content extracted from {original_filename}")
            return False
            
        # 2. Chunk content
        chunks = chunk_text(content)
        print(f"Split {original_filename} into {len(chunks)} chunks.")
        
        # 3. Generate embeddings
        model = get_embedding_model()
        embeddings = model.encode(chunks).tolist()
        
        # 4. Add to ChromaDB
        # Use get_collection to handle safe name resolution
        collection = get_collection(name=repository)
        
        ids = [str(uuid.uuid4()) for _ in range(len(chunks))]
        metadatas = [{"source": original_filename, "chunk_index": i, "type": content_type} for i in range(len(chunks))]
        
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        
        print(f"Successfully added {original_filename} to repository '{repository}'.")
        return True
        
    except Exception as e:
        print(f"Error adding document to KB: {e}")
        return False

def query_knowledge_base(query: str, n_results: int = 3, repositories: List[str] = None, file_filters: List[str] = None) -> List[Dict[str, Any]]:
    """
    Query the knowledge base for relevant context.
    """
    try:
        model = get_embedding_model()
        
        # Generate query embedding
        query_embedding = model.encode([query]).tolist()
        
        all_results = []
        
        # Determine which repositories to search
        repos_to_search = repositories if repositories else list_repositories()
        
        for repo_name in repos_to_search:
            try:
                # Use _get_collection_by_display_name to find the correct collection object
                # because repo_name is likely a display name
                collection = _get_collection_by_display_name(repo_name)
                
                if not collection:
                    print(f"Repository '{repo_name}' not found during query.")
                    continue
                
                # Construct where clause for filtering
                where_clause = None
                if file_filters:
                    # ChromaDB 'where' clause for OR logic on source is a bit tricky if not using $or operator (available in newer versions)
                    # Simple approach: if 1 file, exact match. If multiple, we might need multiple queries or $or
                    # Let's assume file_filters contains exact filenames or partials?
                    # For simplicity, let's try to match 'source' in file_filters
                    if len(file_filters) == 1:
                        where_clause = {"source": file_filters[0]}
                    else:
                        where_clause = {"$or": [{"source": f} for f in file_filters]}
                
                results = collection.query(
                    query_embeddings=query_embedding,
                    n_results=n_results,
                    where=where_clause
                )
                
                if results['documents']:
                    for i in range(len(results['documents'][0])):
                        all_results.append({
                            "content": results['documents'][0][i],
                            "metadata": results['metadatas'][0][i],
                            "distance": results['distances'][0][i] if results['distances'] else 1.0,
                            "repository": repo_name
                        })
            except Exception as e:
                print(f"Error querying repo {repo_name}: {e}")
                
        # Sort combined results by distance (lower is better)
        all_results.sort(key=lambda x: x['distance'])
        
        return all_results[:n_results]
        
    except Exception as e:
        print(f"Error querying KB: {e}")
        return []

def list_documents(repository: str = None) -> List[Dict[str, str]]:
    """
    List all unique documents.
    If repository is None, list from all repositories.
    Returns list of {"name": filename, "repository": repo_name}
    """
    all_files = []
    
    try:
        repos_to_search = [repository] if repository else list_repositories()
        
        for repo in repos_to_search:
            try:
                # Use _get_collection_by_display_name to handle safe names
                collection = _get_collection_by_display_name(repo)
                if not collection:
                    continue
                    
                result = collection.get()
                
                sources = set()
                if result['metadatas']:
                    for meta in result['metadatas']:
                        if 'source' in meta:
                            sources.add(meta['source'])
                
                for source in sources:
                    all_files.append({"name": source, "repository": repo})
                    
            except Exception as e:
                print(f"Error listing documents in {repo}: {e}")
                
        return all_files
    except Exception as e:
        print(f"Error listing documents: {e}")
        return []

def delete_document(filename: str, repository: str = DEFAULT_COLLECTION_NAME) -> bool:
    """Delete all chunks associated with a filename from a repository."""
    try:
        collection = get_collection(name=repository)
        collection.delete(where={"source": filename})
        print(f"Deleted document: {filename} from {repository}")
        return True
    except Exception as e:
        print(f"Error deleting document: {e}")
        return False

def reset_knowledge_base():
    """Clear the entire knowledge base (all repos)."""
    try:
        client = get_chroma_client()
        client.reset() # This might not work on all versions/configs, safer to list and delete
        # Or just delete the directory? No, that breaks the client.
        # Let's delete all collections
        for col in client.list_collections():
            client.delete_collection(col.name)
        print("Knowledge base reset.")
        return True
    except Exception as e:
        print(f"Error resetting KB: {e}")
        return False
