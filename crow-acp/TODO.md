# TO DO


- Fix system prompt to actually include AGENTS.md, render workspace info, add datetime
- Fix prompt_id being hard coded, actually use hash of unrendered
- Add /model selection in ACP
- ~~Include @-ed files in the context through /files or whatever~~
- Add tool calls and executions token emission
- Add callbacks points to agent
- create contracts for requests and responses from callbacks extension SDK so other packages that import crow-acp can interact with the code without inheritance, self injection, or circular imports by
  1.  exposing get/set methods on session data
  2. expose `session/new` and `session/initialize` methods so extension can create new session with new data
  3. expose `session/prompt` with method so extensions/callbacks can use agent's warm kv cache for fast summarization during compaction
- Use AsyncOpenAI client to enable better `session/cancel` behavior
- Load persisted agent from disk using local model. make sure the kv cache is exactly the same

# IDEA 
Just sit down with [agentclientprotocol.com](https://agentclientprotocol.com) and go through the whole thing once just to read, then again with a piece of paper taking notes, then again slower actually implementing in crow-acp.

Pretty much everything I want to do is in here. 

So I added the resource_link blocks to the context and added a `context_fetcher` function to fetch the content of a file and return it as a string.

but yeah I can now chat with an agent in a persistent file and then just copy and paste the conversation into the chat. This is ideal. I mean honestly I think this is going to change how I use the agent.


Think I should have the agent make a PLAN.md and iterate, or do I want to do this by hand and have the agent assist me the way it did when I was creating

Nah I think I just need to do this by hand. Ask the agent as a super sophisticated search engine and debugger to hep me work.


but yeah I think the thing I need to do is to create a bunch of examples of what I want to do in the sandbox and have the echo agent just get progressively more sophisticated. Slash commands, skills, the works, all disconnected from the agent for development velocity.




okay we've got [async-react](./sandbox/async-react/README.md)
