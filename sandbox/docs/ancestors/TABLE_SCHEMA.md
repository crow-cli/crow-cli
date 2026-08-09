We don't want to fetishize narrow tables and do too gd many joins when storage is $0.02/GB 


simple setup

1. session table with tool descriptions, system prompt, stuff to reproduce kv cache

2. wide(is it really?) event table with content, reasoning_content, role, tool_call_id, tool_call_name, tool_call_arguments {THAT YOU CAN PUT IN A JSONB}, DATETIME, conversation_index, session_id


and that's it!
```
role: tool -> look in tool_call_id and content # TOOL RESPONSE, OBVIOUS TOOL RESPONSE
role: assistant -> tool_call_id? — yes -> look in tool_call_name, tool_call_arguments
                        |
                        no -> look in reasoning_content and content
role: user -> just content and metadata [time, session_id, conversation_index]
```


Here are the two tables laid out in Markdown. This structure is built to be "local-LLM first"—meaning it focuses on the metadata you need to maintain a persistent KV cache and a high-fidelity record of every token Crow generates.

### **1. SESSIONS Table**

*The "DNA" of the agent. This table anchors your KV cache. If a row exists with a specific hash, your local engine can skip the prefill.*

| Column | Type | Description |
| --- | --- | --- |
| **session_id** | `TEXT (PK)` | A unique hash of `system_prompt` + `tools`. |
| **system_prompt** | `TEXT` | The static instructions (The "Crow" persona). |
| **tool_definitions** | `JSONB` | The full JSON schemas of all available MCP tools. |
| **request_params** | `JSONB` | `temperature`, `top_p`, `max_tokens`, etc. |
| **model_identifier** | `TEXT` | The exact model version (e.g., `glm-4.7` or `llama-3-70b`). |
| **created_at** | `TIMESTAMP` | When this specific agent configuration was first used. |

---

### **2. EVENTS Table**

*The "Wide" transcript. Every row is a single turn. It captures the thinking, the speaking, and the acting without needing to join five different tables.*

| Column | Type | Role-Specific Usage |
| --- | --- | --- |
| **session_id** | `TEXT (FK)` | Links back to the static session config. |
| **conv_index** | `INT` | The linear order of the conversation (). |
| **timestamp** | `TIMESTAMP` | Precise timing for latency and log-order analysis. |
| **role** | `TEXT` | `user`, `assistant`, `tool`, or your custom `tool_assistant`. |
| **content** | `TEXT` | **User:** input; **Assistant:** verbal; **Tool:** JSON result. |
| **reasoning_content** | `TEXT` | The internal "Thinking" tokens (hidden from user). |
| **tool_call_id** | `TEXT` | The unique ID (links the Assistant's intent to the Tool's result). |
| **tool_call_name** | `TEXT` | The name of the function being executed. |
| **tool_arguments** | `JSONB` | The arguments the model generated for the tool. |
| **metadata** | `JSONB` | Token counts, finish reasons, or local GPU stats. |
