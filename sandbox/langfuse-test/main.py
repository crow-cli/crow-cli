import os

from dotenv import load_dotenv

load_dotenv()

from langfuse import openai

api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")


client = openai.OpenAI(api_key=api_key, base_url=base_url)


messages = [dict(role="user", content="who is president france")]

response = client.chat.completions.create(
    messages=messages, model="unsloth/Qwen3.6-35B-A3B-GGUF:Q8_0"
)

print(response)
