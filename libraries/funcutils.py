import asyncio
import random

async def random_sleep(min_sec: float, max_sec: float):
    await asyncio.sleep(random.uniform(min_sec, max_sec))