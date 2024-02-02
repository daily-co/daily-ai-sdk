import argparse
import asyncio
import os
import re

import aiohttp

from dailyai.services.daily_transport_service import DailyTransportService
from dailyai.services.azure_ai_services import AzureLLMService, AzureTTSService
from dailyai.queue_frame import EndStreamQueueFrame, LLMMessagesQueueFrame
from dailyai.services.elevenlabs_ai_service import ElevenLabsTTSService

from samples.foundational.support.runner import configure

async def main(room_url: str):
    async with aiohttp.ClientSession() as session:
        transport = DailyTransportService(
            room_url,
            None,
            "Say Two Things Bot",
            1,
        )
        transport.mic_enabled = True
        transport.mic_sample_rate = 16000
        transport.camera_enabled = False

        llm = AzureLLMService(api_key=os.getenv("AZURE_CHATGPT_API_KEY"), endpoint=os.getenv("AZURE_CHATGPT_ENDPOINT"), model=os.getenv("AZURE_CHATGPT_MODEL"))
        azure_tts = AzureTTSService(api_key=os.getenv("AZURE_SPEECH_API_KEY"), region=os.getenv("AZURE_SPEECH_REGION"))
        elevenlabs_tts = ElevenLabsTTSService(aiohttp_session=session, api_key=os.getenv("ELEVENLABS_API_KEY"), voice_id=os.getenv("ELEVENLABS_VOICE_ID"))

        messages = [{"role": "system", "content": "tell the user a joke about llamas"}]

        # Start a task to run the LLM to create a joke, and convert the LLM output to audio frames. This task
        # will run in parallel with generating and speaking the audio for static text, so there's no delay to
        # speak the LLM response.
        buffer_queue = asyncio.Queue()
        llm_response_task = asyncio.create_task(
            elevenlabs_tts.run_to_queue(
                buffer_queue,
                llm.run([LLMMessagesQueueFrame(messages)]),
                True,
            )
        )

        @transport.event_handler("on_first_other_participant_joined")
        async def on_first_other_participant_joined(transport):
            await azure_tts.say("My friend the LLM is now going to tell a joke about llamas.", transport.send_queue)

            async def buffer_to_send_queue():
                while True:
                    frame = await buffer_queue.get()
                    await transport.send_queue.put(frame)
                    buffer_queue.task_done()
                    if isinstance(frame, EndStreamQueueFrame):
                        break

            await asyncio.gather(llm_response_task, buffer_to_send_queue())

            await transport.stop_when_done()

        await transport.run()


if __name__ == "__main__":
    (url, token) = configure()
    asyncio.run(main(url))
