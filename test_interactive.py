"""
Interactive MCP Client Test for mem0-mcp server
Run server first: uv run python main.py (SSE mode, no --stdio)
"""
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

MCP_SERVER_URL = "http://localhost:8080/sse"

async def interactive_test():
    print("=" * 60)
    print("🧪 MCP mem0 Interactive Test")
    print("=" * 60)
    print("\nConnecting to server...")
    
    try:
        async with sse_client(MCP_SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Connected!\n")
                
                while True:
                    print("\n" + "=" * 40)
                    print("Choose an option:")
                    print("  1. Remember (add memory)")
                    print("  2. Recall All (list all memories)")
                    print("  3. Recall (semantic search)")
                    print("  4. Forget (delete memories)")
                    print("  5. Exit")
                    print("=" * 40)
                    
                    choice = input("\nYour choice (1-5): ").strip()
                    
                    if choice == "1":
                        print("\nEnter the memory text (or paste code):")
                        print("(Type 'END' on a new line when done)")
                        lines = []
                        while True:
                            line = input()
                            if line.strip() == "END":
                                break
                            lines.append(line)
                        text = "\n".join(lines)
                        
                        if text:
                            print("\n📤 Adding memory...")
                            result = await session.call_tool("remember", {"text": text})
                            print(f"📥 Result: {result.content[0].text}")
                    
                    elif choice == "2":
                        print("\n📤 Getting all memories...")
                        result = await session.call_tool("recall_all", {})
                        print(f"📥 Result:\n{result.content[0].text}")
                    
                    elif choice == "3":
                        query = input("\nEnter search query: ").strip()
                        if query:
                            print(f"\n📤 Searching for '{query}'...")
                            result = await session.call_tool("recall", {"query": query})
                            print(f"📥 Result:\n{result.content[0].text}")
                    
                    elif choice == "4":
                        print("\nFirst, let me show you all memories with their IDs:")
                        result = await session.call_tool("recall_all", {})
                        print(f"\n{result.content[0].text}\n")
                        
                        ids_input = input("Enter memory IDs to delete (comma-separated): ").strip()
                        if ids_input:
                            memory_ids = [id.strip() for id in ids_input.split(",")]
                            print(f"\n📤 Deleting {len(memory_ids)} memory(ies)...")
                            result = await session.call_tool("forget", {"memory_ids": memory_ids})
                            print(f"📥 Result: {result.content[0].text}")
                    
                    elif choice == "5":
                        print("\n👋 Goodbye!")
                        break
                    
                    else:
                        print("❌ Invalid choice. Try again.")
                        
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        print("\nMake sure the server is running in SSE mode:")
        print("  cd ~/code/ultimate-agent-memory")
        print("  uv run python main.py")


if __name__ == "__main__":
    asyncio.run(interactive_test())
