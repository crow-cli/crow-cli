# TO DO


# NEW FEATURES
- agent-client orchestration <- IN PROGRESS
- slash commands <- TODO
- compaction, compaction, compaction <- IN VALIDATION
- skills, skills, skills <- TO DO

# CODE IMPROVEMENTS
- unit testing <- IN PROGRESS
- integration testing <- TODO
- end to end testing <- DONE
- evaluate cancel task vs cancel event to determine which we want to keep and which one we should remove, though tbh it works extremely well right now, I'm not certain this is necessarily suboptimal. maybe overengineered
- remove dead code

# BUG FIXES
- adding a folder causes ACP to crash
- ~~when we cancel a session we do NOT want to include any crap in the messages might yield things like this so we need to revisit cancellation handling and think about letting that last token trickle in after all~~

- ~~apparently zed uses resource instead of resource_link now, which is fine by me lol. implemented. still having trouble doing for when there are multiple types of resource in the message~~

# BACKLOG
- doom loop detection
- Fix intermittent error in terminal tool since upgrade The key insight is that synchronous blocking code (like `time.sleep()` in the terminal polling loop) inside an `async def` function will block the entire event loop - which could cause hangs if the MCP transport needs to do I/O simultaneously. The fix would be `asyncio.to_thread()` or making the polling truly async. 





# DONE
- ~~refactor react~~ <- DONE
- ~~Fix system prompt to actually include AGENTS.md, render workspace info, add datetime~~
- ~~Fix prompt_id being hard coded, actually use hash of unrendered~~
- ~~Include @-ed files in the context through /files or whatever~~
- ~~Add tool calls and executions token emission~~
- ~~Use AsyncOpenAI client to enable better `session/cancel` behavior~~
- ~~test `load_session` using local model~~
- ~~Make different providers part of the actual configuration <- use a toml file or something in ~/.crow~~
- ~~Add different models to NewSessionResponse(config_options<- put model choices here)~~
- ~~Revisit config option setting and build without using session.model_identifier~~
