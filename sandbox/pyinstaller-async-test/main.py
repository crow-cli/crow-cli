"""
Minimal test for PyInstaller + asyncio stdin on Linux.
This reproduces the issue where connect_read_pipe fails with PermissionError.
"""

import asyncio
import platform
import sys

print(f"Python: {sys.version}")
print(f"Platform: {platform.system()}")
print(f"Frozen: {getattr(sys, 'frozen', False)}")
print()


async def test_connect_read_pipe():
    """Test the standard asyncio approach - fails with PyInstaller on Linux."""
    print("Testing connect_read_pipe approach...")
    try:
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_running_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        print("✓ SUCCESS: connect_read_pipe works")

        # Try to read a line
        line = await reader.readline()
        print(f"  Read: {line.decode().strip()}")
        return True
    except Exception as e:
        print(f"✗ FAILED: {type(e).__name__}: {e}")
        return False


async def test_threaded_feeder():
    """Test the threaded stdin feeder approach - should work."""
    print("\nTesting threaded feeder approach...")
    try:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()

        # Start a background thread to read stdin
        import threading

        def blocking_read():
            try:
                while True:
                    data = sys.stdin.buffer.readline()
                    if not data:
                        break
                    loop.call_soon_threadsafe(reader.feed_data, data)
            finally:
                loop.call_soon_threadsafe(reader.feed_eof)

        thread = threading.Thread(target=blocking_read, daemon=True)
        thread.start()

        print("  Thread started, waiting for input...")

        # Try to read a line
        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        print(f"✓ SUCCESS: Threaded feeder works")
        print(f"  Read: {line.decode().strip()}")
        return True
    except asyncio.TimeoutError:
        print("✗ FAILED: Timeout waiting for input")
        return False
    except Exception as e:
        print(f"✗ FAILED: {type(e).__name__}: {e}")
        return False


async def main():
    print("=" * 60)
    print("PyInstaller + Asyncio Stdin Test")
    print("=" * 60)
    print()

    # Test both approaches
    result1 = await test_connect_read_pipe()
    result2 = await test_threaded_feeder()

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  connect_read_pipe: {'✓ Works' if result1 else '✗ Fails'}")
    print(f"  threaded feeder:   {'✓ Works' if result2 else '✗ Fails'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
