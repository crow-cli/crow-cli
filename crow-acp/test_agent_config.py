import asyncio
import logging

from crow_acp.agent import AcpAgent
from crow_acp.config import get_default_config

logging.basicConfig(level=logging.ERROR)


async def test_agent_config():
    print("Initializing Agent...")
    agent = AcpAgent()

    print("\n--- Testing new_session ---")
    new_sess_resp = await agent.new_session(cwd="/tmp", mcp_servers=[])

    print(f"Session ID created: {new_sess_resp.session_id}")
    print("Config Options in NewSessionResponse:")
    for opt in new_sess_resp.config_options:
        print(opt)

    print("\n--- Testing set_config_option ---")
    # Grab the first available model from the options
    first_opt = new_sess_resp.config_options[0].root.options[0]
    test_val = first_opt.value
    print(f"Attempting to set model to: {test_val}")

    set_resp = await agent.set_config_option(
        config_id="model", session_id=new_sess_resp.session_id, value=test_val
    )
    print("Config Options after SetSessionConfigOptionResponse:")
    for opt in set_resp.config_options:
        print(opt)


if __name__ == "__main__":
    asyncio.run(test_agent_config())
