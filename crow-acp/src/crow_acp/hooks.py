"""
Callback hooks for extension points in the agent lifecycle.

This module defines the minimal type signatures for hooks. The actual
implementation is direct function composition - no registry or base classes.

The agent receives hooks as simple functions that mutate SessionState:

    def my_hook(state: SessionState) -> None:
        # Read state.messages, state.session_id, etc.
        # Mutate as needed
        pass

    # Register the hook
    agent.register_hook("pre_request", my_hook)

No classes, no inheritance, no Flask-style init_app pattern.
Just functions that receive state and mutate it.
"""
