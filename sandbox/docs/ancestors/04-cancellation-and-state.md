# Cancellation and State Preservation

## Overview

When users cancel an in-progress generation (especially important with local models that can take 15+ minutes), Crow needs to:
1. Immediately stop generation at the endpoint
2. Persist all tokens received so far
3. Allow seamless resumption without KV cache degradation

## OpenAI/Z.ai SDK Cancellation

### Basic Cancellation Pattern

```python
import asyncio
from openai import AsyncOpenAI

class CancelableGeneration:
    """Wrapper for LLM generation with cancellation support"""
    
    def __init__(self, client: AsyncOpenAI):
        self.client = client
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._accumulated_tokens: dict[str, list[str]] = {}
    
    async def generate_stream(
        self,
        session_id: str,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate with streaming and cancellation support"""
        
        async def generator():
            stream = await self.client.chat.completions.create(
                messages=messages,
                stream=True,
                **kwargs
            )
            
            tokens = []
            try:
                async for chunk in stream:
                    # Handle reasoning content (GLM-4.7)
                    if hasattr(chunk.choices[0].delta, 'reasoning_content'):
                        token = chunk.choices[0].delta.reasoning_content
                    else:
                        token = chunk.choices[0].delta.content or ""
                    
                    tokens.append(token)
                    yield token
            except asyncio.CancelledError:
                print(f"\n[Generation cancelled for session {session_id}]")
                raise
            finally:
                # Save accumulated tokens even if cancelled
                self._accumulated_tokens[session_id] = tokens
        
        # Track the task
        task = asyncio.create_task(generator())
        self._active_tasks[session_id] = task
        
        try:
            async for token in task:
                yield token
        except asyncio.CancelledError:
            # Cancel the underlying HTTP task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise
        finally:
            # Clean up
            del self._active_tasks[session_id]
    
    async def cancel(self, session_id: str) -> bool:
        """Cancel an active generation"""
        if session_id not in self._active_tasks:
            return False
        
        task = self._active_tasks[session_id]
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        return True
    
    def get_accumulated_tokens(self, session_id: str) -> list[str]:
        """Get all tokens received before cancellation"""
        return self._accumulated_tokens.get(session_id, [])
```

### ACP Cancellation Endpoint

```python
# In ACP server
active_generations: dict[str, dict] = {}

@app.post("/sessions/{session_id}/generation", methods=["DELETE"])
async def cancel_generation(session_id: str):
    """
    Cancel in-progress generation for a session.
    
    This stops the HTTP stream to the LLM provider and persists
    all tokens received so far.
    """
    if session_id not in active_generations:
        raise HTTPException(404, "No active generation found")
    
    gen_state = active_generations[session_id]
    
    # Cancel the generation task
    cancelled = await gen_state['cancellation'].cancel(session_id)
    
    if not cancelled:
        raise HTTPException(500, "Failed to cancel generation")
    
    # Get accumulated tokens
    tokens = gen_state['cancellation'].get_accumulated_tokens(session_id)
    
    # Persist partial response
    await persistence.add_message(
        session_id,
        role='assistant',
        content=''.join(tokens),
        metadata={'status': 'cancelled', 'tokens_received': len(tokens)}
    )
    
    # Clean up
    del active_generations[session_id]
    
    return {
        "status": "cancelled",
        "tokens_received": len(tokens),
        "partial_content": ''.join(tokens)
    }
```

## Deep Dive: OpenAI Async SDK Cancellation

The OpenAI Python SDK's async implementation uses `httpx.AsyncClient` under the hood. When cancelling:

```python
# What actually happens when we cancel:

# 1. We set an asyncio.CancelledError on the task
# 2. The SDK catches this and needs to close the HTTP connection
# 3. The SDK's _make_request method handles cancellation

# From the SDK (simplified):
async def _make_request(self, ...):
    async with aiohttp.ClientSession() as session:
        async with session.post(...) as response:
            try:
                async for chunk in response.content:
                    yield chunk
            except asyncio.CancelledError:
                # Here's the important part: we need to close the response
                # to stop receiving more data from the server
                response.close()
                raise

# However, the OpenAI SDK might not properly close the connection,
# so we might need to dive deeper and customize this behavior.
```

### Custom HTTP Client with Proper Cancellation

```python
import httpx
from openai import AsyncOpenAI, httpx as openai_httpx

class CancellableAsyncOpenAI(AsyncOpenAI):
    """
    OpenAI client with proper cancellation support.
    
    The standard SDK might not properly close HTTP connections
    when tasks are cancelled. We override the HTTP client to ensure
    connections are cleaned up.
    """
    
    def __init__(self, **kwargs):
        # Use our custom HTTP client
        if 'http_client' not in kwargs:
            kwargs['http_client'] = openai_httpx.AsyncClient(
                timeout=httpx.Timeout(600.0, connect=60.0),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0
                ),
                follow_redirects=True
            )
        
        super().__init__(**kwargs)
    
    async def _make_request(self, ...):
        """Override to handle cancellation properly"""
        # This is internal to the SDK, so in practice we might need
        # to monkey-patch or submit a PR to the SDK
        pass
```

## KV Cache Persistence (Local Models Only)

When using local models (like through llama.cpp or vLLM), we can minimize the impact of cancellation by preserving the KV cache.

### KV Cache Concepts

The KV cache stores the key-value pairs computed during self-attention. When resuming:
- Without cached KV: Full re-computation (slow, tokens re-processed)
- With cached KV: Only process new tokens (fast)

### With vLLM

```python
from vllm import LLM, SamplingParams

class KVCacheAwareAgent:
    """Agent that preserves KV cache across cancellations"""
    
    def __init__(self, model_name: str):
        # vLLM LLM instance
        self.llm = LLM(
            model=model_name,
            tensor_parallel_size=1,  # Adjust based on GPU/CPU
            gpu_memory_utilization=0.9,
            disable_log_stats=True
        )
        
        self.session_caches: dict[str, Any] = {}
    
    async def generate_with_cache(
        self,
        session_id: str,
        prompts: list[str],
        sampling_params: SamplingParams
    ):
        """
        Generate with KV cache preservation.
        
        The cache is keyed by the prompt hash, so identical prompts
        will reuse the cache.
        """
        # vLLM automatically handles KV caching internally
        # We just need to ensure we're using the same LLM instance
        
        outputs = self.llm.generate(prompts, sampling_params)
        
        return outputs
    
    async def cancel_generation(self, session_id: str):
        """Cancel generation in vLLM"""
        # vLLM doesn't natively support cancellation mid-stream
        # We'd need to:
        # 1. Stop the request at the server level
        # 2. Save partial output
        # 3. When resuming, re-issue the same request
        # 4. The KV cache will be reused automatically
        
        # This is complex and might require vLLM customization
        pass
```

### With llama.cpp

```python
import llama_cpp

class LlamaCppCacheManager:
    """Manage KV cache for llama.cpp"""
    
    def __init__(self, model_path: str):
        self.model = llama_cpp.Llama(
            model_path=model_path,
            n_ctx=4096,  # Context window
            n_gpu_layers=-1,  # Use all available GPU
            verbose=False
        )
        
        # llama.cpp stores KV cache in model object
        # We can save/restore it
    
    def generate_with_progressive_cache(
        self,
        session_id: str,
        prompt: str,
        max_tokens: int = 500
    ):
        """
        Generate with ability to cancel and resume.
        
        llama.cpp doesn't natively support cancellation, but we can:
        1. Generate in chunks
        2. Save state after each chunk
        3. If cancelled, we have partial output
        4. Resume by appending to prompt (inefficient but works)
        """
        all_tokens = []
        
        try:
            # Generate in streaming mode
            for token in self.model(
                prompt,
                max_tokens=max_tokens,
                stream=True,
                echo=False
            ):
                all_tokens.append(token)
                yield token
                
        except KeyboardInterrupt:  # User cancelled
            # We have partial output in all_tokens
            pass
        
        return self.model.detokenize(all_tokens).decode('utf-8')
```

## Simpler Approach: Token Accumulation

For local models where KV cache persistence is complex, we can:

```python
class GenerationTokenState:
    """Manage partial generation state"""
    
    def __init__(self):
        self.partial_outputs: dict[str, str] = {}
        self.partial_messages: dict[str, dict] = {}
    
    async def start_generation(
        self,
        session_id: str,
        messages: list[dict]
    ):
        """Start a new generation"""
        self.partial_outputs[session_id] = ""
        
        # If we have a partial message from cancellation, prepend it
        if session_id in self.partial_messages:
            partial_msg = self.partial_messages[session_id]
            # This partial content is already in the DB
            # We'll continue generating from it
            del self.partial_messages[session_id]
            
            # For local models: we might need to re-process the partial content
            # to rebuild the KV cache, but this is still better than restart
    
    async def accumulate_token(self, session_id: str, token: str):
        """Accumulate tokens as they stream in"""
        if session_id not in self.partial_outputs:
            self.partial_outputs[session_id] = ""
        
        self.partial_outputs[session_id] += token
    
    async def on_cancel(self, session_id: str):
        """Handle cancellation: save partial state"""
        partial = self.partial_outputs.get(session_id, "")
        
        if partial:
            # Save to database
            await persistence.add_message(
                session_id,
                role='assistant',
                content=partial,
                metadata={'status': 'partial', 'cancelled': True}
            )
            
            # Store for potential resumption
            self.partial_messages[session_id] = {
                'role': 'assistant',
                'content': partial,
                'metadata': {'resuming': True}
            }
        
        # Clean up
        if session_id in self.partial_outputs:
            del self.partial_outputs[session_id]
```

## Testing Cancellation

```python
import pytest
import asyncio

async def test_cancellation_during_generation():
    """Test that cancellation properly stops generation and preserves state"""
    agent = CrowAgent()
    
    # Start a long generation
    session_id = await agent.persistence.create_session("/tmp/test")
    
    # Cancel after receiving some tokens
    generation_task = asyncio.create_task(
        agent.process_turn(session_id, "Write a 10000 word essay")
    )
    
    # Wait a bit then cancel
    await asyncio.sleep(2)
    await agent.cancel_generation(session_id)
    
    # Verify partial output was saved
    messages = await agent.persistence.get_messages(session_id)
    
    # Find the assistant message
    assistant_msgs = [m for m in messages if m['role'] == 'assistant']
    assert len(assistant_msgs) > 0
    
    # Should have some content (partial output)
    partial_content = assistant_msgs[-1]['content']
    assert len(partial_content) > 0
    assert assistant_msgs[-1].get('metadata', {}).get('cancelled') is True
    
    print(f"Partial content saved: {len(partial_content)} characters")
```

## Best Practices

1. **Always accumulate tokens as they stream** - don't wait for complete response
2. **Save to database on cancellation** - partial state is valuable
3. **Consider resumption strategy** - for local models, can we avoid re-processing tokens?
4. **Graceful degradation** - if cache can't be preserved, at least don't lose progress
5. **Test both success and cancellation paths** - cancellation is a critical path for long-running local models

## Open Questions

- Can we actually preserve KV cache state across cancellation in llama.cpp?
- Should we store KV cache checkpoints periodically (e.g., every 100 tokens)?
- For remote models, is cancellation even worth it given we'll still pay for consumed tokens?
- How do we handle cancellation during parallel tool execution?
