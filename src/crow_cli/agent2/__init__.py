"""crow agent, ACP v2.

A rewrite, not a shim. :mod:`crow_cli.agent` is the v1 reference and stays
frozen — no ``protocol_version`` flag, no shared code path, no attempt to make
one class speak both protocols. What is reused is reused by *porting* into a
cleaner shape, and what v2 deleted (client fs, client terminal, session modes,
the ``tool_call``/``tool_call_update`` split) is deleted here rather than
carried along with a constant-False capability gate in front of it.

The structural idea, in one paragraph: v1 conflated "the loop has no more
foreground work" with "the session is done" — ``react_loop`` returned, the
generator ended, and nothing could wake it. agent2 splits them.
:mod:`~crow_cli.agent2.react` reports (:class:`~crow_cli.agent2.react.Step`);
:mod:`~crow_cli.agent2.driver` decides, and when it has nothing to run it
emits ``state_update: idle`` and parks on an inbox instead of returning. That
one change is what makes self-wake, the task system and long-running
background work possible, and ACP v2 is just the protocol on top.
"""
