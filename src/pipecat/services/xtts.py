#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import aiohttp

from typing import AsyncGenerator

from pipecat.frames.frames import AudioRawFrame, ErrorFrame, Frame
from pipecat.services.ai_services import TTSService

from loguru import logger

import requests

import numpy as np
import resampy

#####
## The server below can connect to XTTS through a local running docker
##
## Docker command: $ docker run --gpus=all -e COQUI_TOS_AGREED=1 --rm -p 8000:80 ghcr.io/coqui-ai/xtts-streaming-server:latest-cuda121
## 
## You can find more information on the official repo: https://github.com/coqui-ai/xtts-streaming-server
####

SERVER_URL = 'http://localhost:8000'

class XTTSService(TTSService):

    def __init__(
            self,
            *,
            aiohttp_session: aiohttp.ClientSession,
            voice_id: str,
            language: str,
            **kwargs):
        super().__init__(**kwargs)

        self._voice_id = voice_id
        self._language = language
        self._aiohttp_session = aiohttp_session
        self.STUDIO_SPEAKERS = requests.get(SERVER_URL + "/studio_speakers").json()

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"Generating TTS: [{text}]")
        embeddings = self.STUDIO_SPEAKERS[self._voice_id]

        url = SERVER_URL + "/tts_stream"
        
        payload={
            "text": text.replace('.','').replace('*',''),
            "language": self._language,
            "speaker_embedding": embeddings["speaker_embedding"],
            "gpt_cond_latent": embeddings["gpt_cond_latent"],
            "add_wav_header": True,
            "stream_chunk_size": 20,
        }

        await self.start_ttfb_metrics()

        async with self._aiohttp_session.post(url, json=payload) as r:
            if r.status != 200:
                text = await r.text()
                logger.error(f"{self} error getting audio (status: {r.status}, error: {text})")
                yield ErrorFrame(f"Error getting audio (status: {r.status}, error: {text})")
                return
            
            buffer = bytearray()

            async for chunk in r.content.iter_chunked(1024):
                if len(chunk) > 0:
                    await self.stop_ttfb_metrics()
                    # Append new chunk to the buffer
                    buffer.extend(chunk)
                    
                    # Check if buffer has enough data for processing
                    while len(buffer) >= 48000:  # Assuming at least 0.5 seconds of audio data at 24000 Hz
                        # Process the buffer up to a safe size for resampling
                        process_data = buffer[:48000]
                        # Remove processed data from buffer
                        buffer = buffer[48000:]
                        
                        # Convert the byte data to numpy array for resampling
                        audio_np = np.frombuffer(process_data, dtype=np.int16)
                        # Resample the audio from 24000 Hz to 16000 Hz
                        resampled_audio = resampy.resample(audio_np, 24000, 16000)
                        # Convert the numpy array back to bytes
                        resampled_audio_bytes = resampled_audio.astype(np.int16).tobytes()
                        # Create the frame with the resampled audio
                        frame = AudioRawFrame(resampled_audio_bytes, 16000, 1)
                        yield frame

            # Process any remaining data in the buffer
            if len(buffer) > 0:
                audio_np = np.frombuffer(buffer, dtype=np.int16)
                resampled_audio = resampy.resample(audio_np, 24000, 16000)
                resampled_audio_bytes = resampled_audio.astype(np.int16).tobytes()
                frame = AudioRawFrame(resampled_audio_bytes, 16000, 1)
                yield frame