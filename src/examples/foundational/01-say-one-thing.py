import asyncio
import aiohttp
import os
from dailyai.queue_frame import EndStreamQueueFrame

from dailyai.services.daily_transport_service import DailyTransportService
from dailyai.services.elevenlabs_ai_service import ElevenLabsTTSService
from dailyai.services.playht_ai_service import PlayHTAIService

from examples.foundational.support.runner import configure


async def main(room_url):
    async with aiohttp.ClientSession() as session:
        # create a transport service object using environment variables for
        # the transport service's API key, room url, and any other configuration.
        # services can all define and document the environment variables they use.
        # services all also take an optional config object that is used instead of
        # environment variables.
        #
        # the abstract transport service APIs presumably can map pretty closely
        # to the daily-python basic API
        meeting_duration_minutes = 5
        transport = DailyTransportService(
            room_url,
            None,
            "Say One Thing",
            meeting_duration_minutes,
            mic_enabled=True
        )

        """
        tts = ElevenLabsTTSService(
            aiohttp_session=session,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"))
        """
        tts = PlayHTAIService(
            out_queue=transport.send_queue,
            api_key=os.getenv("PLAY_HT_API_KEY"),
            user_id=os.getenv("PLAY_HT_USER_ID"),
            voice_url=os.getenv("PLAY_HT_VOICE_URL"),
        )

        # Register an event handler so we can play the audio when the participant joins.
        @transport.event_handler("on_first_other_participant_joined")
        async def on_first_other_participant_joined(transport, participant):
            nonlocal tts

            await tts.say(
                "Hello there, " + participant["info"]["userName"] + "!"
            )
            await tts.source_queue.put(EndStreamQueueFrame())

            # wait for the output queue to be empty, then leave the meeting
            await transport.stop_when_done()

        await transport.run()
        del(tts)


if __name__ == "__main__":
    (url, token) = configure()
    asyncio.run(main(url))
