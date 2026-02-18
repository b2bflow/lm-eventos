import asyncio
from dotenv import load_dotenv

load_dotenv()
from container.container import Container


container = Container()


async def run_queue_worker():
    # Delega o loop infinito para a classe extraída
    await container.queue.run()


if __name__ == "__main__":
    asyncio.run(run_queue_worker())
