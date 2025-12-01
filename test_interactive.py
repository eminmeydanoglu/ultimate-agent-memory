"""
Interactive MCP Client Test for mem0-mcp server
Run this AFTER restarting the server with: uv run python main.py
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
                    print("  1. Add a memory")
                    print("  2. Get all memories")
                    print("  3. Search memories")
                    print("  4. Exit")
                    print("=" * 40)
                    
                    choice = input("\nYour choice (1-4): ").strip()
                    
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
                            result = await session.call_tool("add_coding_preference", {"text": text})
                            print(f"📥 Result: {result.content[0].text}")
                    
                    elif choice == "2":
                        print("\n📤 Getting all memories...")
                        result = await session.call_tool("get_all_coding_preferences", {})
                        print(f"📥 Result:\n{result.content[0].text}")
                    
                    elif choice == "3":
                        query = input("\nEnter search query: ").strip()
                        if query:
                            print(f"\n📤 Searching for '{query}'...")
                            result = await session.call_tool("search_coding_preferences", {"query": query})
                            print(f"📥 Result:\n{result.content[0].text}")
                    
                    elif choice == "4":
                        print("\n👋 Goodbye!")
                        break
                    
                    else:
                        print("❌ Invalid choice. Try again.")
                        
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        print("\nMake sure the server is running:")
        print("  cd c:\\Users\\eminm\\rag-project\\mem0-mcp")
        print("  uv run python main.py")


if __name__ == "__main__":
    asyncio.run(interactive_test())
