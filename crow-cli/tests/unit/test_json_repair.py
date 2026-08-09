#!/usr/bin/env python3
"""Test the JSON validation and repair in process_tool_call_inputs"""

import sys

sys.path.insert(0, "/home/thomas/src/backup/nid-backup/crow-cli/src")

from crow_cli.agent.react import process_tool_call_inputs


def test_valid_json():
    """Test with valid JSON arguments"""
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": "ls -la"}'],
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 1
    assert len(repaired) == 1
    assert repaired[0] == False  # Not repaired
    assert result[0]["function"]["arguments"] == '{"command": "ls -la"}'
    print("✓ Valid JSON test passed")


def test_malformed_json_missing_close_brace():
    """Test with malformed JSON missing closing brace"""
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": "ls -la"'],  # Missing }
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 1
    assert len(repaired) == 1
    assert repaired[0] == True  # Should have been repaired
    # Should have repaired the JSON
    assert result[0]["function"]["arguments"] == '{"command": "ls -la"}'
    print("✓ Malformed JSON (missing brace) test passed")


def test_malformed_json_incomplete():
    """Test with severely malformed/incomplete JSON"""
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": '],  # Very incomplete
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 1
    assert len(repaired) == 1
    assert repaired[0] == True  # Should have been repaired
    # Should default to empty object
    assert result[0]["function"]["arguments"] == "{}"
    print("✓ Malformed JSON (incomplete) test passed")


def test_fragmented_json():
    """Test with JSON split across multiple fragments"""
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": ', 'ls -la"}'],  # Split
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 1
    assert len(repaired) == 1
    # This will fail validation (not valid JSON) and get repaired to {}
    # because the fragments don't form valid JSON when joined
    assert repaired[0] == True  # Should have been repaired
    assert result[0]["function"]["arguments"] == "{}"
    print("✓ Fragmented JSON test passed")


def test_multiple_tool_calls():
    """Test with multiple tool calls"""
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": "ls"}']
        },
        1: {
            "id": "call_456",
            "function_name": "read",
            "arguments": ['{"path": "/tmp/test.txt"']  # Missing }
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 2
    assert len(repaired) == 2
    assert repaired[0] == False  # First one is valid
    assert repaired[1] == True   # Second one was repaired
    assert result[0]["function"]["arguments"] == '{"command": "ls"}'
    assert result[1]["function"]["arguments"] == '{"path": "/tmp/test.txt"}'
    print("✓ Multiple tool calls test passed")

def test_cancellation_scenario():
    """Test the exact scenario that happens during cancellation - partial tool call"""
    # This simulates what happens when the user cancels mid-stream:
    # The LLM started a tool call but didn't finish the JSON
    tool_calls = {
        0: {
            "id": "call_5f3f6292dddf4b8f88639580",
            "function_name": "terminal",
            "arguments": ['{"command": ']  # Exactly like the error log!
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 1
    assert len(repaired) == 1
    assert repaired[0] == True  # Should have been repaired
    # Should not crash, should default to empty object
    assert result[0]["function"]["arguments"] == '{}'
    print("✓ Cancellation scenario (partial tool call) test passed")

def test_cancellation_with_nested_json():
    """Test cancellation with nested JSON that's incomplete"""
    tool_calls = {
        0: {
            "id": "call_abc123",
            "function_name": "edit",
            "arguments": ['{"file": "test.py", "changes": [{"old": "foo", "new": "bar"']  # Missing }}
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(result) == 1
    assert len(repaired) == 1
    assert repaired[0] == True  # Should have been repaired
    # Should repair the missing braces (1 { and 1 [ missing)
    # Our simple repair just adds closing braces/brackets at the end
    args = result[0]["function"]["arguments"]
    # Just verify it's valid JSON now
    import json
    parsed = json.loads(args)
    assert isinstance(parsed, dict)
    print(f"✓ Cancellation with nested JSON test passed (repaired to: {args})")

def test_repaired_flags():
    """Test that repaired flags are correctly returned"""
    # Test with valid JSON - should not be repaired
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": "ls"}'],
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(repaired) == 1
    assert repaired[0] == False  # Not repaired
    
    # Test with invalid JSON - should be repaired
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": ['{"command": "ls'],  # Missing }
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(repaired) == 1
    assert repaired[0] == True  # Was repaired
    
    # Test with empty arguments - should be repaired
    tool_calls = {
        0: {
            "id": "call_123",
            "function_name": "terminal",
            "arguments": [],  # Empty!
        }
    }
    result, repaired = process_tool_call_inputs(tool_calls)
    assert len(repaired) == 1
    assert repaired[0] == True  # Was repaired (empty string is invalid JSON)
    
    print("✓ Repaired flags test passed")

if __name__ == "__main__":
    test_valid_json()
    test_malformed_json_missing_close_brace()
    test_malformed_json_incomplete()
    test_fragmented_json()
    test_multiple_tool_calls()
    test_cancellation_scenario()
    test_cancellation_with_nested_json()
    test_repaired_flags()
    print("\n✅ All tests passed!")
