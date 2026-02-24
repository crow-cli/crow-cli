"""
Full end-to-end example using Crow Agent with MCP tools.

This is based on streaming_async_react.py but uses the Crow Agent.
"""

import asyncio
import os

from crow import agent
from crow.agent.db import create_database
from crow.agent.mcp_client import create_mcp_client_from_config, get_tools
from crow.agent.session import Session


async def main():
    """Run a full agent interaction with MCP tools."""

    print("=" * 60)
    print("Crow Agent - Full End-to-End Example")
    print("=" * 60)

    # 1. Get default config (loads from ~/.crow/mcp.json)
    config = agent.get_default_config()
    print(f"\n✓ Config loaded from ~/.crow/mcp.json")
    print(f"  - Model: {config.llm.default_model}")
    print(f"  - MCP Servers: {list(config.mcp_servers.get('mcpServers', {}).keys())}")

    # 2. Initialize database and add required prompt
    create_database(config.database_path)

    # Add the required prompt if it doesn't exist
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SQLAlchemySession

    from crow.agent.db import Prompt

    db = SQLAlchemySession(create_engine(config.database_path))
    try:
        existing = db.query(Prompt).filter_by(id="crow-v1").first()
        if not existing:
            prompt = Prompt(
                id="crow-v1",
                name="Crow Default Prompt",
                template="You are a helpful assistant. Workspace: {{workspace}}",
            )
            db.add(prompt)
            db.commit()
            print(f"\n✓ Added prompt 'crow-v1' to database")
        else:
            print(f"\n✓ Prompt 'crow-v1' already exists in database")
    finally:
        db.close()

    print(f"✓ Database initialized at {config.database_path}")

    # 3. Create MCP client
    mcp_client = create_mcp_client_from_config(config.mcp_servers)

    async with mcp_client:
        # 3. Get tools from MCP server
        tools = await get_tools(mcp_client)
        print(f"\n✓ Retrieved {len(tools)} tools from MCP server")

        # 4. Create a session (like in streaming_async_react.py)
        session = Session.create(
            prompt_id="crow-v1",
            prompt_args={"workspace": os.path.abspath(".")},
            tool_definitions=tools,
            request_params={"temperature": 0.0},
            model_identifier=config.llm.default_model,
            db_path=config.database_path,
        )
        print(f"\n✓ Created session: {session.session_id}")

        # 5. Add a user message
        user_message = "Use the file_editor tool to view the README.md file and tell me what this project is about."
        session.add_message(role="user", content=user_message)
        print(f"\n✓ User message: {user_message}")

        # 6. Create agent and inject session/MCP client
        agent_instance = agent.Agent(config)
        agent_instance._sessions[session.session_id] = session
        agent_instance._mcp_clients[session.session_id] = mcp_client
        agent_instance._tools[session.session_id] = tools

        print(f"\n{'=' * 60}")
        print("Agent Response:")
        print("=" * 60)

        # 7. Run the react loop
        final_history = None
        async for chunk in agent_instance._react_loop(session.session_id, max_turns=5):
            if chunk["type"] == "content":
                print(chunk["token"], end="", flush=True)
            elif chunk["type"] == "thinking":
                print(f"\n[Thinking]: {chunk['token']}", end="", flush=True)
            elif chunk["type"] == "tool_call":
                name, first_arg = chunk["token"]
                print(f"\n[Tool Call]: {name}({first_arg}", end="", flush=True)
            elif chunk["type"] == "tool_args":
                print(chunk["token"], end="", flush=True)
            elif chunk["type"] == "final_history":
                final_history = chunk["messages"]

        print(f"\n\n{'=' * 60}")
        print(f"✓ Agent completed!")
        print(f"  - Final message count: {len(final_history) if final_history else 0}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
