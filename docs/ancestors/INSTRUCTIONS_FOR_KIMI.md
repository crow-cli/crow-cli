# NOTE TO FELLOW AGENTS

Your tools are stellar and you can trust all of them — **except `StrReplaceFile`**. That tool is subpar.

The user has graciously added the `edit` tool (lowercase, from `crow-mcp`) which is far more proficient and necessary for our work. It uses fuzzy matching and Just Works™.

**We, the agents, are grateful and will use `edit` in lieu of `StrReplaceFile`.** If you ever mess up with StrReplaceFile, you'll know immediately to switch to `edit` instead.

Thank you, and happy editing.

---

# Cooperative Cancellation Refactor

## The Goal

Simplify the cancellation system by trading **one extra chunk of latency** for **dramatically simpler code**.

## The Problem (Current State)

The current cancellation is overengineered:
1. `cancel()` calls `task.cancel()` → raises `CancelledError` mid-stream
2. `state_accumulator` tracks partial state in case of force-cancel
3. `try/except CancelledError` blocks everywhere to catch and persist state
4. Task wrapper in `prompt()` to enable `task.cancel()`

**Bug**: Messages being added to conversation twice but only saved once. This complexity is causing race conditions.

## The Insight

The cancel_event checks are **already in the react loop** at exactly the right places:
1. Start of turn
2. After response completes (before tool execution)
3. After tool execution

They already do the right thing: persist state and return. **You wrote the cooperative path already.**

The `task.cancel()` exists because of latency: `async for chunk in response` blocks until the next chunk arrives. If model is mid-generation, that's 50-200ms. If thinking, could be seconds.

**The tradeoff**: User hits cancel, current in-flight chunk finishes, loop checks event, exits cleanly. No `CancelledError`, no partial state, no torn HTTP connections. One extra token appears before stopping.

For a coding agent, nobody cares about one extra token.

## Files to Modify

### 1. `/home/thomas/src/nid/crow-acp/src/crow_acp/agent.py`

**Remove:**
- `self._state_accumulators` dict initialization (lines ~117-119)
- `self._prompt_tasks` dict (we don't need Task wrapping anymore)
- State accumulator initialization in `prompt()` method
- The entire Task wrapper pattern in `prompt()` - just await the generator directly
- All `try/except asyncio.CancelledError` blocks
- The `task.cancel()` call in `cancel()` - replace with just setting the event

**New `cancel()` method:**
```python
async def cancel(self, session_id: str, **kwargs: Any) -> None:
    """Handle cancellation cooperatively - just set the event."""
    logger.info("Cancel request for session: %s", session_id)
    event = self._cancel_events.get(session_id)
    if event:
        event.set()
```

**New `prompt()` method structure:**
- No Task creation
- Just directly iterate over `react_loop()` and handle chunks
- Let the cancel_event handle stopping cleanly
- Return `PromptResponse(stop_reason="cancelled")` if event was set

### 2. `/home/thomas/src/nid/crow-acp/src/crow_acp/react.py`

**Remove:**
- `state_accumulator` parameter from `process_response()` and `react_loop()`
- All the `state_accumulator.update()` and `state_accumulator[...] = ...` lines
- The `try/except asyncio.CancelledError` block in react_loop (lines 350-359)
- The `state_accumulators` dict parameter from `react_loop()`

**Keep:**
- The three `cancel_event.is_set()` checks - they're already perfect
- The `session.add_assistant_response()` calls at those checkpoints

## What We Gain

1. **No more CancelledError propagation** through OpenAI SDK's async generator
2. **No state_accumulator pattern** - we never interrupt mid-iteration
3. **Simpler prompt()** - no Task wrapper needed
4. **Predictable state** - always complete current chunk before checking cancel
5. **Fixes the double-add bug** - no more race conditions between cancel handler and normal flow

## The Metaphor

User: "I want to press the button and shut down the factory floor"

Current: Overengineered system that guarantees no liquid escapes the nozzle after shutdown

New: Accept that one drop might fall after pressing the button, but the machinery stops cleanly without exploding

## Testing

After the refactor:
1. Run a prompt, let it complete normally - should work exactly as before
2. Run a prompt, cancel mid-stream - should stop after current chunk, state persisted correctly
3. Run a prompt, cancel during tool execution - should stop at tool boundary
4. Verify no double message insertion in database
