import argparse
from email.mime import image
import logging
import os
import random
import requests
import time
import urllib.parse

from PIL import Image

from dailyai.async_processor.async_processor import (
    ConversationProcessorCollection,
    LLMResponse,
    OrchestratorResponse
)
from dailyai.orchestrator import OrchestratorConfig, Orchestrator
from dailyai.queue_frame import QueueFrame, FrameType
from dailyai.message_handler.message_handler import MessageHandler
from dailyai.services.ai_services import AIServiceConfig
from dailyai.services.azure_ai_services import AzureImageGenService, AzureTTSService, AzureLLMService


class StaticSpriteResponse(OrchestratorResponse):

    def __init__(
        self,
        services,
        message_handler,
        output_queue
    ) -> None:
        super().__init__(services, message_handler, output_queue)
        self.image_bytes: bytes | None = None
        self.filenames = None  # override this in subclasses

    def start_preparation(self) -> None:
        full_path = os.path.join(os.path.dirname(__file__), "sprites/", self.filename)
        print(full_path)

        with Image.open(full_path) as img:
            self.image_bytes = img.tobytes()

    def do_play(self) -> None:
        self.output_queue.put(QueueFrame(FrameType.IMAGE, self.image_bytes))


class IntroSpriteResponse(StaticSpriteResponse):
    def __init__(self, services, message_handler, output_queue) -> None:
        super().__init__(services, message_handler, output_queue)
        self.filename = "intro.png"


class WaitingSpriteResponse(StaticSpriteResponse):
    def __init__(self, services, message_handler, output_queue) -> None:
        super().__init__(services, message_handler, output_queue)
        self.filename = "waiting.png"


class AnimatedSpriteLLMResponse(LLMResponse):
    def __init__(self, services, message_handler, output_queue) -> None:
        super().__init__(services, message_handler, output_queue)
        self.filenames = ["talk-1.png", "talk-2.png"]
        self.image_bytes = []

    def start_preparation(self) -> None:
        super().start_preparation()

        for filename in self.filenames:
            full_path = os.path.join(os.path.dirname(__file__), "sprites/", filename)
            print(full_path)

            with Image.open(full_path) as img:
                self.image_bytes.append(img.tobytes())

    def get_frames_from_tts_response(self, audio_frame) -> list[QueueFrame]:
        return [
            QueueFrame(FrameType.AUDIO, audio_frame),
            QueueFrame(FrameType.IMAGE, random.choice(self.image_bytes))
        ]


def add_bot_to_room(room_url, token, expiration) -> None:

    # A simple prompt for a simple sample.
    message_handler = MessageHandler(
        """
        You are a sample bot in a WebRTC session. You'll receive input as transcriptions of user's
        speech, and your responses will be converted to audio via a TTS service.
        Answer user's questions and be friendly, and if you can, give some ideas about how someone
        could use a bot like you in a more in-depth way. Because your responses will be spoken,
        try to keep them short.
    """
    )

    # Use Azure services for the TTS, image generation, and LLM.
    # Note that you'll need to set the following environment variables:
    # - AZURE_SPEECH_SERVICE_KEY
    # - AZURE_SPEECH_SERVICE_REGION
    # - AZURE_CHATGPT_KEY
    # - AZURE_CHATGPT_ENDPOINT
    # - AZURE_CHATGPT_DEPLOYMENT_ID
    #
    # This demo doesn't use image generation, but if you extend it to do so,
    # you'll also need to set:
    # - AZURE_DALLE_KEY
    # - AZURE_DALLE_ENDPOINT
    # - AZURE_DALLE_DEPLOYMENT_ID

    services = AIServiceConfig(
        tts=AzureTTSService(), image=AzureImageGenService(), llm=AzureLLMService()
    )

    sprite_conversation_processors = ConversationProcessorCollection(
        introduction=IntroSpriteResponse,
        waiting=WaitingSpriteResponse,
        response=AnimatedSpriteLLMResponse,
    )

    orchestrator_config = OrchestratorConfig(
        room_url=room_url,
        token=token,
        bot_name="Simple Bot",
        expiration=expiration,
    )

    logging.basicConfig(format=f"%(levelno)s %(asctime)s %(message)s")
    logger: logging.Logger = logging.getLogger("dailyai")
    logger.setLevel(logging.DEBUG)

    orchestrator = Orchestrator(
        orchestrator_config,
        services,
        message_handler,
        sprite_conversation_processors
    )
    orchestrator.start()

    # When the orchestrator's done, we need to shut it down,
    # and the various services and handlers we've created.
    orchestrator.stop()
    message_handler.shutdown()

    services.tts.close()
    services.image.close()
    services.llm.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple Daily Bot Sample")
    parser.add_argument("-u", "--url", type=str, required=True, help="URL of the Daily room")
    parser.add_argument(
        "-k", "--apikey", type=str, required=True, help="Daily API Key (needed to create token)"
    )

    args: argparse.Namespace = parser.parse_args()

    # Create a meeting token for the given room with an expiration 1 hour in the future.
    room_name: str = urllib.parse.urlparse(args.url).path[1:]
    expiration: float = time.time() + 60 * 60

    res: requests.Response = requests.post(
        f"https://api.daily.co/v1/meeting-tokens",
        headers={"Authorization": f"Bearer {args.apikey}"},
        json={
            "properties": {"room_name": room_name, "is_owner": True, "exp": expiration}
        },
    )

    if res.status_code != 200:
        raise Exception(f'Failed to create meeting token: {res.status_code} {res.text}')

    token: str = res.json()['token']

    add_bot_to_room(args.url, token, expiration)
