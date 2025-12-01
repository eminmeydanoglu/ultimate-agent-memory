import os
import sys
from datetime import datetime
import warnings

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

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn
from mem0 import Memory
from dotenv import load_dotenv
import json

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

# Initialize mem0 with local hybrid config
mem0_client = Memory.from_config(LOCAL_HYBRID_CONFIG)
DEFAULT_USER_ID = "cursor_mcp"

@mcp.tool(
    description="""Add a new coding preference to mem0. This tool stores code snippets, implementation details,
    and coding patterns for future reference. Store every code snippet. When storing code, you should include:
    - Complete code with all necessary imports and dependencies
    - Language/framework version information (e.g., "Python 3.9", "React 18")
    - Full implementation context and any required setup/configuration
    - Detailed comments explaining the logic, especially for complex sections
    - Example usage or test cases demonstrating the code
    - Any known limitations, edge cases, or performance considerations
    - Related patterns or alternative approaches
    - Links to relevant documentation or resources
    - Environment setup requirements (if applicable)
    - Error handling and debugging tips
    The preference will be indexed for semantic search and can be retrieved later using natural language queries."""
)
async def add_coding_preference(text: str) -> str:
    """Add a new coding preference to mem0.

    This tool is designed to store code snippets, implementation patterns, and programming knowledge.
    When storing code, it's recommended to include:
    - Complete code with imports and dependencies
    - Language/framework information
    - Setup instructions if needed
    - Documentation and comments
    - Example usage

    Args:
        text: The content to store in memory, including code, documentation, and context
    """
    try:
        # Local Memory uses .add() directly with text content
        mem0_client.add(text, user_id=DEFAULT_USER_ID)
        return f"Successfully added preference: {text[:100]}..."
    except Exception as e:
        return f"Error adding preference: {str(e)}"

@mcp.tool(
    description="""Retrieve all stored coding preferences for the default user. Call this tool when you need 
    complete context of all previously stored preferences. This is useful when:
    - You need to analyze all available code patterns
    - You want to check all stored implementation examples
    - You need to review the full history of stored solutions
    - You want to ensure no relevant information is missed
    Returns a comprehensive list of:
    - Code snippets and implementation patterns
    - Programming knowledge and best practices
    - Technical documentation and examples
    - Setup and configuration guides
    Results are returned in JSON format with metadata."""
)
async def get_all_coding_preferences() -> str:
    """Get all coding preferences for the default user.

    Returns a JSON formatted list of all stored preferences, including:
    - Code implementations and patterns
    - Technical documentation
    - Programming best practices
    - Setup guides and examples
    Each preference includes metadata about when it was created and its content type.
    """
    try:
        memories = mem0_client.get_all(user_id=DEFAULT_USER_ID)
        # Handle both list and dict response formats
        if isinstance(memories, dict) and "results" in memories:
            flattened_memories = [memory.get("memory", memory) for memory in memories["results"]]
        elif isinstance(memories, list):
            flattened_memories = [memory.get("memory", memory) for memory in memories]
        else:
            flattened_memories = memories
        return json.dumps(flattened_memories, indent=2)
    except Exception as e:
        return f"Error getting preferences: {str(e)}"

@mcp.tool(
    description="""Search through stored coding preferences using semantic search. This tool should be called 
    for EVERY user query to find relevant code and implementation details. It helps find:
    - Specific code implementations or patterns
    - Solutions to programming problems
    - Best practices and coding standards
    - Setup and configuration guides
    - Technical documentation and examples
    The search uses natural language understanding to find relevant matches, so you can
    describe what you're looking for in plain English. Always search the preferences before 
    providing answers to ensure you leverage existing knowledge."""
)
async def search_coding_preferences(query: str) -> str:
    """Search coding preferences using semantic search.

    The search is powered by natural language understanding, allowing you to find:
    - Code implementations and patterns
    - Programming solutions and techniques
    - Technical documentation and guides
    - Best practices and standards
    Results are ranked by relevance to your query.

    Args:
        query: Search query string describing what you're looking for. Can be natural language
              or specific technical terms.
    """
    try:
        memories = mem0_client.search(query, user_id=DEFAULT_USER_ID)
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

def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can server the provied mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
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
        mcp_server = mcp._mcp_server
        starlette_app = create_starlette_app(mcp_server, debug=True)
        uvicorn.run(starlette_app, host=args.host, port=args.port)
