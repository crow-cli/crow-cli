#!/usr/bin/env python3
import sys
sys.path.insert(0, 'refs/python-sdk/src')
from acp import Agent
import inspect

print('Agent methods:')
for name, method in inspect.getmembers(Agent, predicate=inspect.isfunction):
    if not name.startswith('_'):
        sig = inspect.signature(method)
        print(f'  {name}{sig}')
