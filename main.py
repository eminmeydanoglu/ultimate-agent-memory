import os
import sys
from datetime import datetime
import warnings
import atexit
import signal

# Check if running in stdio mode (for VS Code/Copilot) - suppress print output
STDIO_MODE = '--stdio' in sys.argv

# In stdio mode, suppress all warnings to stderr as well
if STDIO_MODE:
    warnings.filterwarnings("ignore")
    # Redirect stderr to devnull to suppress library warnings
    import io
    sys.stderr = io.StringIO()

def log_print(*args, **kwargs):
    """Print only when not in stdio mode (stdio mode needs clean stdout for JSON-RPC)"""
    if not STDIO_MODE:
        print(*args, **kwargs)

# Fix for sqlite3 on Linux systems (must be before chromadb import)
# Windows has sqlite3 bundled with Python, so this is only needed on Linux
if sys.platform == "linux":
    try:
        __import__('pysqlite3')
        sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
    except ImportError:
        pass  # pysqlite3 not installed, use system sqlite3

# Core imports (always needed)
from mcp.server.fastmcp import FastMCP
from mcp.server import Server
from mem0 import Memory
from dotenv import load_dotenv
import json

# SSE-only imports - loaded lazily only when SSE mode is used
# This speeds up stdio mode startup significantly
def get_sse_imports():
    """Lazy load SSE-related imports only when needed"""
    from starlette.applications import Starlette
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.routing import Mount, Route
    import uvicorn
    return Starlette, SseServerTransport, Request, Mount, Route, uvicorn

load_dotenv()

# ============== Gemini API Logging ==============
GEMINI_LOG_FILE = "./gemini_log.jsonl"

def log_gemini_request(operation: str, input_data: dict, output_data: dict, error: str = None):
    """Log Gemini API requests to a JSONL file"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "input": input_data,
        "output": output_data,
        "error": error
    }
    try:
        with open(GEMINI_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        log_print(f"[GeminiLog] Error writing log: {e}")

# ============== Fix mem0 Gemini Bug for 2.5 Flash ==============
# Bug: tool_config is always set even when tools is None
# This causes "400 Function calling config is set without function_declarations"
try:
    from mem0.llms.gemini import GeminiLLM
    from google.generativeai.types import content_types
    import google.generativeai as genai
    
    _original_generate_response = GeminiLLM.generate_response
    
    def fixed_generate_response(self, messages, response_format=None, tools=None, tool_choice="auto"):
        """Fixed version that only sets tool_config when tools are provided"""
        params = {
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }

        if response_format is not None and response_format["type"] == "json_object":
            params["response_mime_type"] = "application/json"
            if "schema" in response_format:
                params["response_schema"] = response_format["schema"]
        
        # FIX: Only set tool_config if tools are actually provided
        tool_config = None
        if tools and tool_choice:
            tool_config = content_types.to_tool_config(
                {
                    "function_calling_config": {
                        "mode": tool_choice,
                        "allowed_function_names": (
                            [tool["function"]["name"] for tool in tools] if tool_choice == "any" else None
                        ),
                    }
                }
            )
        
        # Log the request
        input_data = {
            "model": self.client.model_name if hasattr(self.client, 'model_name') else str(self.client),
            "messages": str(messages)[:2000],
            "tools": str(tools)[:500] if tools else None,
            "tool_choice": tool_choice
        }
        
        try:
            response = self.client.generate_content(
                contents=self._reformat_messages(messages),
                tools=self._reformat_tools(tools),
                generation_config=genai.GenerationConfig(**params),
                tool_config=tool_config,
            )
            
            result = self._parse_response(response, tools)
            
            # Log the response
            output_data = {
                "response": str(result)[:2000]
            }
            log_gemini_request("llm_generate", input_data, output_data)
            
            return result
        except Exception as e:
            log_gemini_request("llm_generate", input_data, {}, error=str(e))
            raise
    
    GeminiLLM.generate_response = fixed_generate_response
    log_print("[GeminiFix] Patched mem0 GeminiLLM.generate_response for 2.5 Flash compatibility")
    
except ImportError as e:
    log_print(f"[GeminiFix] Could not patch mem0 GeminiLLM: {e}")
except Exception as e:
    log_print(f"[GeminiFix] Failed to patch: {e}")

# Monkey-patch google.generativeai to intercept embedding API calls
try:
    import google.generativeai as genai
    
    # Patch embed_content function for logging
    _original_embed_content = genai.embed_content
    
    def logged_embed_content(*args, **kwargs):
        input_data = {
            "args": [str(a)[:500] for a in args],
            "kwargs": {k: str(v)[:500] for k, v in kwargs.items()}
        }
        try:
            result = _original_embed_content(*args, **kwargs)
            output_data = {
                "embedding_length": len(result.get('embedding', [])) if isinstance(result, dict) else "N/A"
            }
            log_gemini_request("embed_content", input_data, output_data)
            return result
        except Exception as e:
            log_gemini_request("embed_content", input_data, {}, error=str(e))
            raise
    
    genai.embed_content = logged_embed_content
    log_print(f"[GeminiLog] Embedding logging enabled -> {GEMINI_LOG_FILE}")
    
except ImportError:
    log_print("[GeminiLog] google.generativeai not found, logging disabled")
except Exception as e:
    log_print(f"[GeminiLog] Failed to patch embeddings: {e}")
# ============== End Gemini Patches ==============

# Initialize FastMCP server for mem0 tools
mcp = FastMCP("mem0-mcp")

# Define Local Hybrid Config - data stays local, LLM is remote
LOCAL_HYBRID_CONFIG = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "agent_memory",
            "path": "./local_mem0_db",  # Persistent local folder
        }
    },
    "llm": {
        "provider": "gemini",
        "config": {
            "model": "gemini-2.5-flash",
            "api_key": os.environ.get("GOOGLE_API_KEY")
        }
    },
    "embedder": {
        "provider": "gemini",
        "config": {
            "model": "models/text-embedding-004",
            "api_key": os.environ.get("GOOGLE_API_KEY")
        }
    }
}

# Lazy-loaded mem0 client - initialized on first use
_mem0_client = None
DEFAULT_USER_ID = "cursor_mcp"

def get_mem0_client():
    """Get or initialize the mem0 client (lazy loading for faster startup)"""
    global _mem0_client
    if _mem0_client is None:
        log_print("[Mem0] Initializing memory client...")
        _mem0_client = Memory.from_config(LOCAL_HYBRID_CONFIG)
        log_print("[Mem0] Memory client ready!")
    return _mem0_client

def cleanup():
    """Cleanup function called on exit - closes ChromaDB connection properly"""
    global _mem0_client
    if _mem0_client is not None:
        log_print("[Mem0] Cleaning up...")
        try:
            # ChromaDB client cleanup if available
            if hasattr(_mem0_client, 'vector_store') and hasattr(_mem0_client.vector_store, 'client'):
                client = _mem0_client.vector_store.client
                if hasattr(client, '_client') and hasattr(client._client, 'close'):
                    client._client.close()
            _mem0_client = None
            log_print("[Mem0] Cleanup complete!")
        except Exception as e:
            log_print(f"[Mem0] Cleanup error (ignored): {e}")

# Register cleanup handlers
atexit.register(cleanup)

def signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown"""
    log_print(f"\n[Server] Received signal {signum}, shutting down...")
    cleanup()
    sys.exit(0)

# Register signal handlers (Windows compatible)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
if sys.platform == "win32":
    signal.signal(signal.SIGBREAK, signal_handler)

@mcp.tool(
    description="""Remember information for future reference. This tool stores code snippets, implementation details,
    coding patterns, user preferences, and any knowledge worth preserving. When storing code, include:
    - Complete code with all necessary imports and dependencies
    - Language/framework version information (e.g., "Python 3.9", "React 18")
    - Full implementation context and any required setup/configuration
    - Detailed comments explaining the logic, especially for complex sections
    - Example usage or test cases demonstrating the code
    - Any known limitations, edge cases, or performance considerations
    The memory will be indexed for semantic search and can be recalled later using natural language queries."""
)
async def remember(text: str) -> str:
    """Remember information for future reference.

    Store code snippets, implementation patterns, programming knowledge, or any information.
    
    Args:
        text: The content to remember - code, documentation, preferences, or any knowledge
    """
    try:
        # Local Memory uses .add() directly with text content
        client = get_mem0_client()
        client.add(text, user_id=DEFAULT_USER_ID)
        return f"Successfully added preference: {text[:100]}..."
    except Exception as e:
        return f"Error adding preference: {str(e)}"

@mcp.tool(
    description="""Recall all stored memories. Call this tool when you need complete context of everything remembered.
    This is useful when:
    - You need to see all available knowledge
    - You want to review the full history of stored information
    - You want to ensure no relevant information is missed
    Returns a comprehensive list of all memories in JSON format with metadata including memory IDs for deletion."""
)
async def recall_all() -> str:
    """Recall all stored memories.

    Returns a JSON formatted list of all memories, including:
    - Memory ID (for deletion with forget)
    - Memory content
    - Creation timestamp
    """
    try:
        client = get_mem0_client()
        memories = client.get_all(user_id=DEFAULT_USER_ID)
        # Handle both list and dict response formats - preserve full memory objects with IDs
        if isinstance(memories, dict) and "results" in memories:
            formatted_memories = [{"id": m.get("id"), "memory": m.get("memory"), "created_at": m.get("created_at")} for m in memories["results"]]
        elif isinstance(memories, list):
            formatted_memories = [{"id": m.get("id"), "memory": m.get("memory"), "created_at": m.get("created_at")} for m in memories]
        else:
            formatted_memories = memories
        return json.dumps(formatted_memories, indent=2)
    except Exception as e:
        return f"Error getting preferences: {str(e)}"

@mcp.tool(
    description="""Forget specific memories by their IDs. Use this tool to remove memories that are:
    - No longer relevant or outdated
    - Incorrect or contain errors
    - Duplicates of other memories
    - Requested by the user to be forgotten
    You can delete one or multiple memories at once by providing their IDs.
    Use recall_all first to see available memories and their IDs."""
)
async def forget(memory_ids: list[str]) -> str:
    """Forget specific memories by their IDs.

    Args:
        memory_ids: List of memory IDs to delete. Get IDs from recall_all.
    """
    try:
        client = get_mem0_client()
        deleted = []
        errors = []
        for memory_id in memory_ids:
            try:
                client.delete(memory_id)
                deleted.append(memory_id)
            except Exception as e:
                errors.append(f"{memory_id}: {str(e)}")
        
        result = f"Successfully deleted {len(deleted)} memory(ies)."
        if errors:
            result += f" Errors: {'; '.join(errors)}"
        return result
    except Exception as e:
        return f"Error deleting memories: {str(e)}"

@mcp.tool(
    description="""Recall memories using semantic search. This tool should be called for EVERY user query
    to find relevant stored knowledge. It helps find:
    - Specific code implementations or patterns
    - Solutions to programming problems
    - User preferences and information
    - Technical documentation and examples
    The search uses natural language understanding to find relevant matches, so you can
    describe what you're looking for in plain English. Always recall before providing answers
    to ensure you leverage existing knowledge."""
)
async def recall(query: str) -> str:
    """Recall memories using semantic search.

    The search is powered by natural language understanding, allowing you to find relevant
    stored knowledge. Results are ranked by relevance to your query.

    Args:
        query: What you're looking for - can be natural language or specific terms.
    """
    try:
        client = get_mem0_client()
        memories = client.search(query, user_id=DEFAULT_USER_ID)
        # Handle both list and dict response formats
        if isinstance(memories, dict) and "results" in memories:
            flattened_memories = [memory.get("memory", memory) for memory in memories["results"]]
        elif isinstance(memories, list):
            flattened_memories = [memory.get("memory", memory) for memory in memories]
        else:
            flattened_memories = memories
        return json.dumps(flattened_memories, indent=2)
    except Exception as e:
        return f"Error searching preferences: {str(e)}"

def create_starlette_app(mcp_server: Server, *, debug: bool = False):
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    # Lazy load SSE imports only when this function is called
    Starlette, SseServerTransport, Request, Mount, Route, _ = get_sse_imports()
    
    sse = SseServerTransport("/messages/")

    async def handle_sse(request) -> None:
        async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run MCP server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (SSE mode)')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on (SSE mode)')
    parser.add_argument('--stdio', action='store_true', help='Run in stdio mode for VS Code integration')
    args = parser.parse_args()

    if args.stdio:
        # Run in stdio mode (for VS Code/Copilot integration)
        mcp.run(transport='stdio')
    else:
        # Run in SSE mode (for HTTP-based clients)
        # Load SSE imports only in SSE mode
        _, _, _, _, _, uvicorn = get_sse_imports()
        mcp_server = mcp._mcp_server
        starlette_app = create_starlette_app(mcp_server, debug=True)
        uvicorn.run(starlette_app, host=args.host, port=args.port)
