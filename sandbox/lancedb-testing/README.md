# LanceDB Persistence & Token Integrity Test Plan

## Objective
To identify and resolve a suspected token loss bug occurring during the serialization and deserialization of conversation history. The bug is suspected to manifest as a subtle "drift" in message content (e.g., lost whitespace, newlines, or special tokens) when transitioning from in-memory state to persisted storage and back.

## Hypothesis
The current SQLite/JSON-based persistence layer in `crow-cli` introduces subtle discrepancies in the `content` or `reasoning_content` strings of assistant messages. These discrepancies are likely caused by how message blocks are joined or how JSON serialization handles specific character sequences (especially around `<think>` tags). This causes the LLM to receive a prompt that is bit-for-bit different from the one generated during the live stream, leading to token count mismatches and context drift.

## Testing Strategy: "Bit-for-Bit" Verification

We will use a standalone sandbox environment to decouple the persistence logic from the complex `react_loop` and agent orchestration.

### 1. Strict Schema Definition
We will use `lancedb.pydantic.LanceModel` to define a strict, typed schema for messages. This eliminates the ambiguity of "loose" JSON blobs and ensures that every field (including nested tool calls) is explicitly typed.

### 2. Ground Truth Comparison
The test suite will follow this protocol:
1. **Generate High-Entropy State**: Create a set of messages containing:
    * Extreme whitespace variations (multiple newlines, tabs, trailing spaces).
    * Multimodal content (simulated).
    * Complex tool call arguments (nested JSON, special characters).
    * Reasoning content blocks with `<think>`/`</think>` boundaries.
2. **In-Memory Baseline**: Store these messages in a standard Python `list[dict]`.
3. **LanceDB Persistence**: Write the messages to a LanceDB table.
4. **Deserialization**: Retrieve the messages from LanceDB.
5. **The Audit**: Perform a deep, bit-for-bit equality check between the **In-Memory Baseline** and the **Deserialized Data**. 
    * We will not just check `len(content)`, but the exact string equality.
    * We will check cumulative character counts across the entire session.

### 3. Validation Scenarios
* **Single Message Roundtrip**: Ensure a single complex message survives.
* **Multi-Turn Accumulation**: Ensure a long conversation (100+ turns) maintains total character count parity.
* **Cancellation/Partial State**: Ensure that partially completed assistant responses (captured during a cancellation) are persisted and retrieved with 100% fidelity.

## Success Criteria
The persistence layer is considered verified if and only if:
`In-Memory Message List == Deserialized Message List` (Deep Equality)
for all high-entropy edge cases.
