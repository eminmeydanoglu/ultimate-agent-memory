#!/usr/bin/env python3
"""
Memory Manager - A simple web interface for managing mem0 memories.
Run with: python memory_manager.py
Then open http://localhost:5000 in your browser.
"""

import os
import sys
import json
from flask import Flask, render_template_string, jsonify, request

# Fix for sqlite3 on Linux systems
if sys.platform == "linux":
    try:
        __import__('pysqlite3')
        sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
    except ImportError:
        pass

from mem0 import Memory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Same config as main.py
LOCAL_HYBRID_CONFIG = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "agent_memory",
            "path": "./local_mem0_db",
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

DEFAULT_USER_ID = "cursor_mcp"
_mem0_client = None

def get_mem0_client():
    global _mem0_client
    if _mem0_client is None:
        print("[Mem0] Initializing memory client...")
        _mem0_client = Memory.from_config(LOCAL_HYBRID_CONFIG)
        print("[Mem0] Memory client ready!")
    return _mem0_client

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Memory Manager - Mem0 MCP</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e4e4e4;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #00d9ff;
            font-size: 2.5em;
            text-shadow: 0 0 20px rgba(0, 217, 255, 0.3);
        }
        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .card h2 {
            color: #00d9ff;
            margin-bottom: 16px;
            font-size: 1.3em;
        }
        .add-memory-form {
            display: flex;
            gap: 12px;
        }
        .add-memory-form textarea {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            font-size: 14px;
            resize: vertical;
            min-height: 80px;
            transition: border-color 0.3s;
        }
        .add-memory-form textarea:focus {
            outline: none;
            border-color: #00d9ff;
        }
        .add-memory-form textarea::placeholder {
            color: rgba(255, 255, 255, 0.4);
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #00d9ff, #0099cc);
            color: #000;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 217, 255, 0.3);
        }
        .btn-danger {
            background: linear-gradient(135deg, #ff4757, #cc3344);
            color: #fff;
        }
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(255, 71, 87, 0.3);
        }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        .memory-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .memory-item {
            background: rgba(0, 0, 0, 0.3);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            align-items: flex-start;
            gap: 16px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            transition: all 0.3s;
        }
        .memory-item:hover {
            border-color: rgba(0, 217, 255, 0.3);
            background: rgba(0, 0, 0, 0.4);
        }
        .memory-checkbox {
            width: 20px;
            height: 20px;
            accent-color: #00d9ff;
            cursor: pointer;
            margin-top: 2px;
        }
        .memory-content {
            flex: 1;
        }
        .memory-text {
            color: #fff;
            line-height: 1.5;
            word-break: break-word;
            white-space: pre-wrap;
        }
        .memory-meta {
            font-size: 12px;
            color: rgba(255, 255, 255, 0.4);
            margin-top: 8px;
        }
        .memory-id {
            font-family: monospace;
            background: rgba(0, 217, 255, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            color: #00d9ff;
        }
        .actions-bar {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            align-items: center;
        }
        .select-all-container {
            display: flex;
            align-items: center;
            gap: 8px;
            color: rgba(255, 255, 255, 0.6);
        }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: rgba(255, 255, 255, 0.4);
        }
        .empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 16px;
            opacity: 0.3;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: rgba(255, 255, 255, 0.6);
        }
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #00d9ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 16px 24px;
            border-radius: 12px;
            color: #fff;
            font-weight: 500;
            z-index: 1000;
            animation: slideIn 0.3s ease;
        }
        .toast.success {
            background: linear-gradient(135deg, #00d9ff, #0099cc);
            color: #000;
        }
        .toast.error {
            background: linear-gradient(135deg, #ff4757, #cc3344);
        }
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        .search-box {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
        }
        .search-box input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            font-size: 14px;
        }
        .search-box input:focus {
            outline: none;
            border-color: #00d9ff;
        }
        .search-box input::placeholder {
            color: rgba(255, 255, 255, 0.4);
        }
        .stats {
            display: flex;
            gap: 24px;
            margin-bottom: 20px;
        }
        .stat-item {
            background: rgba(0, 217, 255, 0.1);
            padding: 16px 24px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #00d9ff;
        }
        .stat-label {
            font-size: 12px;
            color: rgba(255, 255, 255, 0.6);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 Memory Manager</h1>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-value" id="totalMemories">-</div>
                <div class="stat-label">Total Memories</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="selectedCount">0</div>
                <div class="stat-label">Selected</div>
            </div>
        </div>
        
        <div class="card">
            <h2>➕ Add New Memory</h2>
            <div class="add-memory-form">
                <textarea id="newMemory" placeholder="Enter a new memory to store... (e.g., coding preferences, patterns, knowledge)"></textarea>
                <button class="btn btn-primary" onclick="addMemory()">Add Memory</button>
            </div>
        </div>
        
        <div class="card">
            <h2>📚 Stored Memories</h2>
            
            <div class="search-box">
                <input type="text" id="searchQuery" placeholder="Search memories..." onkeyup="filterMemories()">
                <button class="btn btn-secondary" onclick="loadMemories()">🔄 Refresh</button>
            </div>
            
            <div class="actions-bar">
                <label class="select-all-container">
                    <input type="checkbox" class="memory-checkbox" id="selectAll" onclick="toggleSelectAll()">
                    Select All
                </label>
                <button class="btn btn-danger" onclick="deleteSelected()">🗑️ Delete Selected</button>
            </div>
            
            <div id="memoryList" class="memory-list">
                <div class="loading">
                    <div class="spinner"></div>
                    Loading memories...
                </div>
            </div>
        </div>
    </div>

    <script>
        let memories = [];
        let selectedIds = new Set();
        
        async function loadMemories() {
            const listEl = document.getElementById('memoryList');
            listEl.innerHTML = '<div class="loading"><div class="spinner"></div>Loading memories...</div>';
            
            try {
                const response = await fetch('/api/memories');
                const data = await response.json();
                memories = data.memories || [];
                renderMemories();
                document.getElementById('totalMemories').textContent = memories.length;
            } catch (error) {
                listEl.innerHTML = '<div class="empty-state">Error loading memories: ' + error.message + '</div>';
            }
        }
        
        function renderMemories() {
            const listEl = document.getElementById('memoryList');
            const searchQuery = document.getElementById('searchQuery').value.toLowerCase();
            
            const filtered = memories.filter(m => 
                m.memory.toLowerCase().includes(searchQuery) ||
                (m.id && m.id.toLowerCase().includes(searchQuery))
            );
            
            if (filtered.length === 0) {
                listEl.innerHTML = `
                    <div class="empty-state">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                        <p>${searchQuery ? 'No memories match your search' : 'No memories stored yet'}</p>
                    </div>
                `;
                return;
            }
            
            listEl.innerHTML = filtered.map(m => `
                <div class="memory-item" data-id="${m.id}">
                    <input type="checkbox" class="memory-checkbox" 
                           ${selectedIds.has(m.id) ? 'checked' : ''} 
                           onchange="toggleSelect('${m.id}')">
                    <div class="memory-content">
                        <div class="memory-text">${escapeHtml(m.memory)}</div>
                        <div class="memory-meta">
                            ID: <span class="memory-id">${m.id || 'N/A'}</span>
                            ${m.created_at ? ' • Created: ' + formatDate(m.created_at) : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function filterMemories() {
            renderMemories();
        }
        
        function toggleSelect(id) {
            if (selectedIds.has(id)) {
                selectedIds.delete(id);
            } else {
                selectedIds.add(id);
            }
            updateSelectedCount();
        }
        
        function toggleSelectAll() {
            const selectAllEl = document.getElementById('selectAll');
            if (selectAllEl.checked) {
                memories.forEach(m => selectedIds.add(m.id));
            } else {
                selectedIds.clear();
            }
            renderMemories();
            updateSelectedCount();
        }
        
        function updateSelectedCount() {
            document.getElementById('selectedCount').textContent = selectedIds.size;
        }
        
        async function addMemory() {
            const textarea = document.getElementById('newMemory');
            const text = textarea.value.trim();
            
            if (!text) {
                showToast('Please enter a memory to add', 'error');
                return;
            }
            
            try {
                const response = await fetch('/api/memories', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await response.json();
                
                if (data.success) {
                    showToast('Memory added successfully!', 'success');
                    textarea.value = '';
                    loadMemories();
                } else {
                    showToast('Error: ' + data.error, 'error');
                }
            } catch (error) {
                showToast('Error adding memory: ' + error.message, 'error');
            }
        }
        
        async function deleteSelected() {
            if (selectedIds.size === 0) {
                showToast('No memories selected', 'error');
                return;
            }
            
            if (!confirm(`Are you sure you want to delete ${selectedIds.size} memory(ies)?`)) {
                return;
            }
            
            const btn = document.querySelector('.btn-danger');
            const originalText = btn.innerHTML;
            btn.innerHTML = 'Deleting...';
            btn.disabled = true;
            
            try {
                const response = await fetch('/api/memories', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: Array.from(selectedIds) })
                });
                const data = await response.json();
                
                if (data.success) {
                    // Remove deleted items from local state immediately
                    const deletedIds = Array.from(selectedIds);
                    memories = memories.filter(m => !deletedIds.includes(m.id));
                    
                    // Clear selection
                    selectedIds.clear();
                    updateSelectedCount();
                    
                    // Re-render list
                    renderMemories();
                    document.getElementById('totalMemories').textContent = memories.length;
                    
                    showToast(`Deleted ${data.deleted} memory(ies)`, 'success');
                    
                    // Still fetch fresh data in background to be sure
                    loadMemories();
                } else {
                    showToast('Error: ' + data.error, 'error');
                }
            } catch (error) {
                showToast('Error deleting memories: ' + error.message, 'error');
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }
        
        function showToast(message, type) {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        }
        
        // Load memories on page load
        loadMemories();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/memories', methods=['GET'])
def get_memories():
    try:
        client = get_mem0_client()
        memories = client.get_all(user_id=DEFAULT_USER_ID)
        
        # Handle both list and dict response formats
        if isinstance(memories, dict) and "results" in memories:
            formatted = [{"id": m.get("id"), "memory": m.get("memory"), "created_at": m.get("created_at")} for m in memories["results"]]
        elif isinstance(memories, list):
            formatted = [{"id": m.get("id"), "memory": m.get("memory"), "created_at": m.get("created_at")} for m in memories]
        else:
            formatted = []
        
        return jsonify({"memories": formatted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/memories', methods=['POST'])
def add_memory():
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        
        if not text:
            return jsonify({"success": False, "error": "Text is required"}), 400
        
        client = get_mem0_client()
        client.add(text, user_id=DEFAULT_USER_ID)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/memories', methods=['DELETE'])
def delete_memories():
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        
        if not ids:
            return jsonify({"success": False, "error": "No IDs provided"}), 400
        
        client = get_mem0_client()
        deleted = 0
        errors = []
        
        for memory_id in ids:
            try:
                client.delete(memory_id)
                deleted += 1
            except Exception as e:
                errors.append(f"{memory_id}: {str(e)}")
        
        return jsonify({
            "success": True,
            "deleted": deleted,
            "errors": errors
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/memories/search', methods=['POST'])
def search_memories():
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({"error": "Query is required"}), 400
        
        client = get_mem0_client()
        memories = client.search(query, user_id=DEFAULT_USER_ID)
        
        if isinstance(memories, dict) and "results" in memories:
            formatted = [{"id": m.get("id"), "memory": m.get("memory"), "score": m.get("score")} for m in memories["results"]]
        elif isinstance(memories, list):
            formatted = [{"id": m.get("id"), "memory": m.get("memory"), "score": m.get("score")} for m in memories]
        else:
            formatted = []
        
        return jsonify({"memories": formatted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("🧠 Memory Manager - Mem0 MCP")
    print("=" * 50)
    print("Starting server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
