import asyncio

from dailyai.queue_frame import LLMMessagesQueueFrame, QueueFrame, TextQueueFrame
from dailyai.services.ai_services import AIService

from typing import AsyncGenerator, List


class QueueTee:
    async def run_to_queue_and_generate(
        self,
        output_queue: asyncio.Queue,
        generator: AsyncGenerator[QueueFrame, None]
    ) -> AsyncGenerator[QueueFrame, None]:
        async for frame in generator:
            await output_queue.put(frame)
            yield frame

    async def run_to_queues(
        self,
        output_queues: List[asyncio.Queue],
        generator: AsyncGenerator[QueueFrame, None]
    ):
        async for frame in generator:
            for queue in output_queues:
                await queue.put(frame)


class LLMContextAggregator(AIService):
    def __init__(
            self,
            messages: list[dict],
            role: str,
            bot_participant_id=None,
            complete_sentences=True):
        self.messages = messages
        self.bot_participant_id = bot_participant_id
        self.role = role
        self.sentence = ""
        self.complete_sentences = complete_sentences

    async def process_frame(self, frame: QueueFrame) -> AsyncGenerator[QueueFrame, None]:
        # TODO: split up transcription by participant
        if isinstance(frame, TextQueueFrame):
            if self.complete_sentences:
                self.sentence += frame.text
                if self.sentence.endswith((".", "?", "!")):
                    self.messages.append({"role": self.role, "content": self.sentence})
                    self.sentence = ""
                    yield LLMMessagesQueueFrame(self.messages)
            else:
                self.messages.append({"role": self.role, "content": frame.text})
                yield LLMMessagesQueueFrame(self.messages)

        yield frame
