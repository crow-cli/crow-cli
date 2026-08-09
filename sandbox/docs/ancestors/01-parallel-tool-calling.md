# Parallel Tool Calling in Crow

## Motivation

Crow's architecture prioritizes parallel execution of tools, especially for search operations. When an agent needs to gather information from multiple sources or perform multiple related queries, launching them in parallel significantly reduces latency compared to sequential execution.

## Implementation Strategy

### ReAct Loop with Parallel Tool Execution

The standard ReAct pattern we're using with MCP:

```python
# Single turn from user input to LLM response
async def process_turn(messages: list[dict], mcp_client: Client) -> list[dict]:
    """
    Process a single turn of conversation with parallel tool execution.
    
    Args:
        messages: Current conversation history
        mcp_client: MCP client for tool execution
        
    Returns:
        Updated conversation history with tool responses
    """
    # 1. Get LLM response with tool calls
    response = oai_client.chat.completions.create(
        model="glm-4.7",
        messages=messages,
        tools=build_openai_tools(mcp_client),
        stream=True
    )
    
    # 2. Parse streaming response
    assistant_content = []
    tool_calls_by_id = {}
    
    for chunk in response:
        if hasattr(chunk.choices[0].delta, 'reasoning_content'):
            # Handle reasoning chunks (GLM-4.7 specific)
            reasoning = chunk.choices[0].delta.reasoning_content
            print(reasoning, end="", flush=True)
            assistant_content.append(reasoning_content_to_markdown(reasoning))
        elif chunk.choices[0].delta.content:
            # Normal content
            content = chunk.choices[0].delta.content
            print(content, end="", flush=True)
            assistant_content.append(content)
        elif chunk.choices[0].delta.tool_calls:
            # Collect tool calls
            for call in chunk.choices[0].delta.tool_calls:
                tool_calls_by_id[call.id] = {
                    'function_name': call.function.name,
                    'arguments': call.function.arguments
                }
    
    # Append assistant message to history
    messages.append({
        'role': 'assistant',
        'content': ''.join(assistant_content)
    })
    
    # 3. Execute tools in PARALLEL using asyncio.gather
    if tool_calls_by_id:
        tool_call_inputs = []
        tool_tasks = []
        
        # Build tool calls and tasks
        for tool_call_id, tool_call in tool_calls_by_id.items():
            tool_call_inputs.append({
                'id': tool_call_id,
                'type': 'function',
                'function': {
                    'name': tool_call['function_name'],
                    'arguments': tool_call['arguments']
                }
            })
            
            # Schedule async execution
            task = asyncio.create_task(
                mcp_client.call_tool(
                    tool_call['function_name'],
                    json.loads(tool_call['arguments'])
                )
            )
            tool_tasks.append(task)
        
        # Append tool calls to assistant message
        messages.append({'role': 'assistant', 'tool_calls': tool_call_inputs})
        
        # Execute all tools in parallel and collect results
        tool_results = await asyncio.gather(*tool_tasks)
        
        # Append tool responses to conversation
        for tool_call_id, result in zip(tool_calls_by_id.keys(), tool_results):
            messages.append({
                'role': 'tool',
                'tool_call_id': tool_call_id,
                'content': result.content[0].text
            })
    
    return messages
```

### Key Differences from Sequential Execution

**Sequential (what we had):**
```python
for tool_call_id, tool_call in tool_calls_by_id.items():
    result = await client.call_tool(...)  # Wait for each one
    messages.append(...)
    # Then make next LLM call
```

**Parallel (what we want):**
```python
# Schedule all tool calls at once
tasks = [client.call_tool(...) for tool_call_id, tool_call in tool_calls_by_id.items()]
# Execute all in parallel
results = await asyncio.gather(*tasks)
# Then make final LLM call with all results
```

### Parallel Tool Calls in OpenAI/Z.ai API

The `parallel_tool_calls=True` parameter tells the LLM it can return multiple tool calls in a single response instead of splitting them across multiple turns. This is especially useful for:

- Multiple search queries with different perspectives
- Gathering information from different sources
- Running batched operations

```python
response = oai_client.chat.completions.create(
    model="glm-4.7",
    messages=messages,
    tools=[openai_tool],
    parallel_tool_calls=True,  # Encourage parallel tool calls
    stream=True
)
```

## Resource Considerations

While parallel execution is faster, it can be resource-intensive. Consider:

1. **Rate limiting**: SearXNG and external APIs may have rate limits
2. **Memory**: Parallel tool results consume memory simultaneously
3. **Network bandwidth**: Concurrent requests may saturate connection

## Prompt Engineering for Parallel Tools

To encourage the agent to use parallel tool calls effectively, include in system prompt:

```
When you need to gather information from multiple sources or perform multiple related searches, 
make all tool calls in a single response. This allows them to execute in parallel, reducing latency.

Example good pattern:
- Search for "machine learning papers" on ArXiv
- Search for the same topic on GitHub
- Search for code examples

All these can be done in one function call block, saving time.
```

## Search-Specific Parallel Execution

For search operations, the agent should be encouraged to:

1. **Search multiple sources**: ArXiv (academic), PubMed (medical), GitHub (code), general web (SearXNG)
2. **Search with variations**: Different query formulations, synonyms, related terms
3. **Search in parallel**: Instead of sequential refinement, launch all searches and then synthesize

System prompt guidance:

```
When searching for information:
- Launch multiple searches across different sources simultaneously (ArXiv, GitHub, web, PubMed)
- Use varied query formulations to capture different angles
- Don't wait for results before launching additional searches
- Synthesize results from all sources in your final response

This is much faster than iteratively refining searches based on results.
```

## Testing Parallel Execution

```python
import asyncio
import time

async def test_parallel_tools():
    """Verify that tools actually execute in parallel"""
    start_time = time.time()
    
    # Simulate 3 searches that each take 2 seconds
    async def slow_search(query):
        await asyncio.sleep(2)
        return f"Results for {query}"
    
    # Sequential execution: ~6 seconds
    seq_start = time.time()
    for q in ["query1", "query2", "query3"]:
        await slow_search(q)
    seq_time = time.time() - seq_start
    
    # Parallel execution: ~2 seconds
    par_start = time.time()
    await asyncio.gather(*(slow_search(q) for q in ["query1", "query2", "query3"]))
    par_time = time.time() - par_start
    
    print(f"Sequential: {seq_time:.2f}s, Parallel: {par_time:.2f}s")
    # Should see ~3x speedup
```

## Open Questions

- Should we impose a maximum number of parallel tool calls to prevent resource exhaustion?
- How do we handle partial failures in parallel tool execution?
- Should certain tools (like file writes) be forced to execute sequentially for safety?
