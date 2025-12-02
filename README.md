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

Open http://localhost:5000

## Configuration

Create `.env` with your LLM provider API key:

```bash
GOOGLE_API_KEY=your_api_key_here
```

## Requirements

- Python ≥3.12
- LLM API key

