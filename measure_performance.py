
import asyncio
import aiohttp
import time
import json
import sys

URL = "http://localhost:8000/check_youtube"
HANDLE = "PewDiePie" # Example popular channel

async def check_custom(session, handle):
    start = time.time()
    try:
        async with session.post(URL, json={"handle": handle}) as response:
            first_byte = time.time()
            # print(f"Time to first byte: {first_byte - start:.4f}s")
            
            lines = 0
            async for line in response.content:
                if line:
                    lines += 1
            
            end = time.time()
            return first_byte - start, end - first_byte, end - start, lines
    except Exception as e:
        print(f"Error: {e}")
        return 0, 0, 0, 0

async def main():
    print(f"Benchmarking {URL} with handle {HANDLE}...")
    async with aiohttp.ClientSession() as session:
        ttfb, download_time, total_time, lines = await check_custom(session, HANDLE)
        
    print(f"TTFB: {ttfb:.4f}s")
    print(f"Stream Duration: {download_time:.4f}s")
    print(f"Total Time: {total_time:.4f}s")
    print(f"Total Response Lines: {lines}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        HANDLE = sys.argv[1]
    asyncio.run(main())
