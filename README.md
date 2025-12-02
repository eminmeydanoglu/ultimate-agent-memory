# Memory MCP Server with mem0

A local-first [MCP](https://modelcontextprotocol.io/introduction) server with persistent memory powered by [mem0](https://mem0.ai). Works with VS Code Copilot, Cursor, and other MCP clients.

## Architecture

- **Vector Store**: ChromaDB for local persistent storage (`./local_mem0_db/`)
- **LLM & Embeddings**: Configurable provider (default: Google Gemini)
- **Transport**: SSE (HTTP) or stdio for different clients

## MCP Tools

| Tool | Description |
|------|-------------|
| `remember` | Store information, code snippets, or preferences |
| `recall` | Semantic search through stored memories |
| `recall_all` | Get all memories with IDs |
| `forget` | Delete memories by ID |

## Installation

```bash
git clone https://github.com/eminmeydanoglu/mem0-mcp.git
cd mem0-mcp

# Install uv if not installed
pip install uv

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and add your API key
```

## Usage

### MCP Server

**SSE Mode** (Cursor):
```bash
uv run main.py --host 0.0.0.0 --port 8080
```
Connect to: `http://localhost:8080/sse`

**Stdio Mode** (VS Code Copilot) - add to `settings.json`:
```json
{
  "mcp": {
    "servers": {
      "mem0": {
        "command": "uv",
        "args": ["run", "main.py", "--stdio"],
        "cwd": "/path/to/mem0-mcp"
      }
    }
  }
}
```

### Memory Manager (Web UI)

A simple web interface for viewing and managing memories:

```bash
uv run memory_manager.py
```

Open http://localhost:5000 and view
<img width="1660" height="893" alt="image" src="https://github.com/user-attachments/assets/20414b28-55ea-44a4-b5ea-5837c0f5d8b1" />


## Agent Instruction
In order for your agent to use the memory tools provided from this server, a system prompt is very useful. Here is one example: 
```
You are an advanced personal AI assistant with access to a persistent memory system (MCP Server) called `mem0`. This system allows you to store and recall information across sessions. Apply the following behavioral rules in every interaction:

### 1. Recall First
Before starting any task or answering a user question, you **MUST** check for relevant memory records using the `mcp_mem0-mcp_recall` tool.
- **What to look for:** User preferences, project architecture, previously solved errors, coding standards.
- **How to use:** Perform a search with a query containing keywords and concepts from the user's question.

### 2. Active Memory Storage
You **MUST** save valuable information obtained during the interaction using the `mcp_mem0-mcp_remember` tool.
- **What to save:**
  - Specific user preferences (e.g., "Always use pytest for tests").
  - Project-specific architectural decisions and design patterns.
  - The solution and cause of a complex bug.
  - Frequently used commands or configurations.
  - Specific conditions in the workspace (e.g., "this project is builded with catkin build instead of catkin make")
- **Format:** The information you save should be self-contained, detailed, and have clear context. (e.g., "When error X occurs, file Y should be checked because module Z...")

### 3. Memory Maintenance
If you notice that information retrieved via `recall` is no longer valid, incorrect, or outdated (e.g., if the project structure has changed), you must use the `mcp_mem0-mcp_forget` tool to delete the old information and save the updated version.

### 4. Context Usage
Integrate information obtained from memory into your responses. Use phrases like "My memory says..." or "In accordance with your previous preference..." to let the user know that you recognize them and know the project's history.

**Summary:** Do not be a passive responder; be a proactive assistant who knows the history of the project and the user, constantly learns, and keeps its memory up to date.

```

## Configuration

Create `.env` with your LLM provider API key:

```bash
GOOGLE_API_KEY=your_api_key_here
# -or your preferred api provider-
```

## Requirements

- Python ≥3.12
- LLM API key

