"""Run async steps inline or start a flow in the background."""

import asyncio
from functools import partial

from autodef import FlowStoppedError, flow, step


async def fetch(url: str) -> str:
    await asyncio.sleep(0.1)
    return f"content from {url}"


@flow
async def fetch_all(urls: list[str]) -> list[str]:
    return [await step(partial(fetch, url), name=f"fetch_{index}") for index, url in enumerate(urls)]


async def main() -> None:
    completed = await fetch_all(["https://example.com", "https://example.org"])
    print(completed.result())

    background = fetch_all.start(["one", "two", "three"])
    await asyncio.sleep(0.15)
    background.stop()

    try:
        await background
    except FlowStoppedError:
        print(f"Background flow stopped with status: {background.status}")


if __name__ == "__main__":
    asyncio.run(main())
