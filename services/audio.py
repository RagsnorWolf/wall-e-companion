"""Audio Service — Wall-E Companion Software.

Microphone capture, speech recognition (Whisper), text-to-speech (Piper),
sound effect playback, voice activity detection.
"""

from __future__ import annotations

import asyncio
import io
import os
import wave
import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, List
from loguru import logger
from core.hardware import get_hardware_config

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logger.warning("PyAudio not available - audio service will use mock")

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("faster-whisper not available - STT disabled")

try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logger.warning("Piper TTS not available - TTS disabled")


@dataclass
class AudioChunk:
    """Audio data chunk."""
    data: bytes
    timestamp: float
    sample_rate: int
    channels: int


@dataclass
class Transcription:
    """Speech recognition result."""
    text: str
    language: str
    confidence: float
    segments: list
    processing_time: float


class AudioService:
    """Audio I/O and processing service."""

    def __init__(self, config_path: Optional[str] = None):
        self.hw = get_hardware_config(config_path)
        self.running = False

        # PyAudio
        self.pyaudio: Optional[pyaudio.PyAudio] = None
        self.mic_stream: Optional[pyaudio.Stream] = None
        self.speaker_stream: Optional[pyaudio.Stream] = None

        # Models (lazy loaded)
        self.whisper_model: Optional[WhisperModel] = None
        self.piper_voice: Optional[PiperVoice] = None

        # Audio buffers
        self.mic_buffer: List[AudioChunk] = []
        self.max_buffer_chunks = 100  # ~2 seconds at 16kHz

        # Callbacks
        self.transcription_callbacks: List[Callable[[Transcription], Awaitable[None]]] = []
        self.vad_callbacks: List[Callable[[bool], Awaitable[None]]] = []  # voice activity
        self.audio_level_callbacks: List[Callable[[float], Awaitable[None]]] = []

        # VAD
        self.vad_threshold = 0.01
        self.silence_chunks = 0
        self.speech_chunks = 0
        self.is_speaking = False

        # TTS queue
        self.tts_queue: asyncio.Queue = asyncio.Queue()
        self.tts_task: Optional[asyncio.Task] = None

        # Sound effects
        self.sound_effects: dict[str, bytes] = {}
        self.sounds_dir = "sounds"

    async def start(self):
        """Initialize audio system."""
        if not PYAUDIO_AVAILABLE:
            logger.warning("Running in mock audio mode")
            self.running = True
            return

        await self._init_pyaudio()
        await self._init_models()

        self.running = True
        self.tts_task = asyncio.create_task(self._tts_loop())
        logger.info("Audio service started")

    async def stop(self):
        """Stop audio system."""
        self.running = False

        if self.mic_stream:
            self.mic_stream.stop_stream()
            self.mic_stream.close()
            self.mic_stream = None

        if self.speaker_stream:
            self.speaker_stream.stop_stream()
            self.speaker_stream.close()
            self.speaker_stream = None

        if self.pyaudio:
            self.pyaudio.terminate()
            self.pyaudio = None

        if self.tts_task:
            self.tts_task.cancel()
            try:
                await self.tts_task
            except asyncio.CancelledError:
                pass

        logger.info("Audio service stopped")

    async def _init_pyaudio(self):
        """Initialize PyAudio streams."""
        mic_cfg = self.hw.audio
        speaker_cfg = self.hw.audio

        self.pyaudio = pyaudio.PyAudio()

        # Input stream (microphone)
        self.mic_stream = self.pyaudio.open(
            format=pyaudio.paInt16,
            channels=mic_cfg.mic_channels,
            rate=mic_cfg.mic_sample_rate,
            input=True,
            input_device_index=mic_cfg.mic_device_index,
            frames_per_buffer=mic_cfg.mic_chunk_size,
            stream_callback=self._mic_callback,
        )

        # Output stream (speaker)
        self.speaker_stream = self.pyaudio.open(
            format=pyaudio.paInt16,
            channels=speaker_cfg.speaker_channels,
            rate=speaker_cfg.speaker_sample_rate,
            output=True,
            output_device_index=speaker_cfg.speaker_device_index,
            frames_per_buffer=speaker_cfg.speaker_chunk_size,
        )

        self.mic_stream.start_stream()
        logger.info("PyAudio streams started")

    def _mic_callback(self, in_data, frame_count, time_info, status):
        """PyAudio input callback (runs in audio thread)."""
        if not self.running:
            return (None, pyaudio.paComplete)

        chunk = AudioChunk(
            data=in_data,
            timestamp=time.time(),
            sample_rate=self.hw.audio.mic_sample_rate,
            channels=self.hw.audio.mic_channels,
        )

        # Calculate audio level for VAD
        import numpy as np
        audio_data = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(audio_data**2))

        # Simple VAD
        if rms > self.vad_threshold:
            self.speech_chunks += 1
            self.silence_chunks = 0
            if self.speech_chunks >= 3 and not self.is_speaking:
                self.is_speaking = True
                asyncio.run_coroutine_threadsafe(self._notify_vad(True), asyncio.get_event_loop())
        else:
            self.silence_chunks += 1
            self.speech_chunks = 0
            if self.silence_chunks >= 10 and self.is_speaking:
                self.is_speaking = False
                asyncio.run_coroutine_threadsafe(self._notify_vad(False), asyncio.get_event_loop())

        # Notify audio level
        asyncio.run_coroutine_threadsafe(self._notify_audio_level(float(rms)), asyncio.get_event_loop())

        # Buffer for STT
        self.mic_buffer.append(chunk)
        if len(self.mic_buffer) > self.max_buffer_chunks:
            self.mic_buffer.pop(0)

        return (None, pyaudio.paContinue)

    async def _notify_vad(self, is_speech: bool):
        for cb in self.vad_callbacks:
            try:
                await cb(is_speech)
            except Exception as e:
                logger.error(f"VAD callback error: {e}")

    async def _notify_audio_level(self, level: float):
        for cb in self.audio_level_callbacks:
            try:
                await cb(level)
            except Exception as e:
                logger.error(f"Audio level callback error: {e}")

    async def _init_models(self):
        """Load Whisper and Piper models."""
        models = self.hw.models

        # Whisper
        if WHISPER_AVAILABLE:
            def load_whisper():
                return WhisperModel(
                    models.whisper_model_size,
                    device=models.whisper_device,
                    compute_type="int8" if models.whisper_device == "cpu" else "float16",
                )

            loop = asyncio.get_event_loop()
            self.whisper_model = await loop.run_in_executor(None, load_whisper)
            logger.info(f"Whisper model loaded: {models.whisper_model_size}")

        # Piper TTS
        if PIPER_AVAILABLE:
            def load_piper():
                return PiperVoice.load(models.piper_voice)

            loop = asyncio.get_event_loop()
            self.piper_voice = await loop.run_in_executor(None, load_piper)
            logger.info(f"Piper voice loaded: {models.piper_voice}")

    async def _tts_loop(self):
        """Process TTS queue."""
        while self.running:
            try:
                text, callbacks = await self.tts_queue.get()
                await self._synthesize_and_play(text)
                for cb in callbacks:
                    try:
                        await cb()
                    except Exception:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TTS loop error: {e}")

    async def _synthesize_and_play(self, text: str):
        """Synthesize speech and play it."""
        if not PIPER_AVAILABLE or self.piper_voice is None:
            logger.warning("TTS not available")
            return

        models = self.hw.models

        def synthesize():
            audio_chunks = []
            for chunk in self.piper_voice.synthesize_stream_raw(
                text,
                length_scale=models.piper_length_scale,
                noise_scale=models.piper_noise_scale,
                noise_w=models.piper_noise_w,
            ):
                audio_chunks.append(chunk)
            return b"".join(audio_chunks)

        loop = asyncio.get_event_loop()
        audio_data = await loop.run_in_executor(None, synthesize)

        # Play audio
        await self.play_audio(audio_data, self.hw.audio.speaker_sample_rate)

    async def play_audio(self, audio_data: bytes, sample_rate: int = 22050):
        """Play raw PCM audio data."""
        if not PYAUDIO_AVAILABLE or not self.speaker_stream:
            return

        def play():
            self.speaker_stream.write(audio_data)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, play)

    async def speak(self, text: str, on_done: Optional[Callable[[], Awaitable[None]]] = None):
        """Queue text for speech synthesis."""
        callbacks = [on_done] if on_done else []
        await self.tts_queue.put((text, callbacks))

    async def play_sound(self, sound_name: str, volume: float = 1.0):
        """Play a sound effect."""
        # Load sound if not cached
        if sound_name not in self.sound_effects:
            await self._load_sound(sound_name)

        if sound_name in self.sound_effects:
            # Apply volume
            import numpy as np
            audio = np.frombuffer(self.sound_effects[sound_name], dtype=np.int16).astype(np.float32)
            audio = audio * volume
            audio = np.clip(audio, -32768, 32767).astype(np.int16)
            await self.play_audio(audio.tobytes())

    async def _load_sound(self, sound_name: str):
        """Load sound effect from file."""
        sound_path = os.path.join(self.sounds_dir, f"{sound_name}.wav")
        if os.path.exists(sound_path):
            with wave.open(sound_path, 'rb') as wf:
                self.sound_effects[sound_name] = wf.readframes(wf.getnframes())
        else:
            # Generate simple beep
            import numpy as np
            duration = 0.2
            freq = 800 if "beep" in sound_name else 400
            t = np.linspace(0, duration, int(22050 * duration))
            wave_data = np.sin(2 * np.pi * freq * t) * 32767 * 0.3
            self.sound_effects[sound_name] = wave_data.astype(np.int16).tobytes()

    def get_mic_buffer(self) -> bytes:
        """Get concatenated microphone buffer for STT."""
        return b"".join(chunk.data for chunk in self.mic_buffer)

    async def transcribe_buffer(self) -> Optional[Transcription]:
        """Transcribe current microphone buffer."""
        if not WHISPER_AVAILABLE or self.whisper_model is None:
            return None

        audio_data = self.get_mic_buffer()
        if len(audio_data) < 16000:  # Less than 1 second
            return None

        def transcribe():
            segments, info = self.whisper_model.transcribe(
                audio_data,
                language=self.hw.models.whisper_language,
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text for seg in segments)
            return text, info.language, segments

        loop = asyncio.get_event_loop()
        start = time.time()
        text, language, segments = await loop.run_in_executor(None, transcribe)
        processing_time = time.time() - start

        transcription = Transcription(
            text=text.strip(),
            language=language,
            confidence=1.0,  # Whisper doesn't give confidence directly
            segments=[{"text": s.text, "start": s.start, "end": s.end} for s in segments],
            processing_time=processing_time,
        )

        for cb in self.transcription_callbacks:
            try:
                await cb(transcription)
            except Exception as e:
                logger.error(f"Transcription callback error: {e}")

        return transcription

    async def listen_for_wake_word(self, wake_words: List[str] = None) -> Optional[str]:
        """Listen for wake word (simple implementation)."""
        wake_words = wake_words or ["wall-e", "wall e", "eva", "robot"]

        transcription = await self.transcribe_buffer()
        if transcription and transcription.text:
            text_lower = transcription.text.lower()
            for word in wake_words:
                if word in text_lower:
                    return word
        return None

    # Callback registration
    def on_transcription(self, callback: Callable[[Transcription], Awaitable[None]]):
        self.transcription_callbacks.append(callback)

    def on_vad(self, callback: Callable[[bool], Awaitable[None]]):
        self.vad_callbacks.append(callback)

    def on_audio_level(self, callback: Callable[[float], Awaitable[None]]):
        self.audio_level_callbacks.append(callback)


class MockAudioService(AudioService):
    """Mock audio service for testing without hardware."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__(config_path)
        self.mock_transcriptions: List[str] = []
        self.mock_vad = False

    async def start(self):
        self.running = True
        self.tts_task = asyncio.create_task(self._tts_loop())
        logger.info("Mock audio service started")

    async def speak(self, text: str, on_done: Optional[Callable[[], Awaitable[None]]] = None):
        logger.info(f"[MOCK TTS] {text}")
        if on_done:
            await on_done()

    async def play_sound(self, sound_name: str, volume: float = 1.0):
        logger.info(f"[MOCK SOUND] {sound_name}")

    async def listen_for_wake_word(self, wake_words: List[str] = None) -> Optional[str]:
        if self.mock_transcriptions:
            text = self.mock_transcriptions.pop(0)
            wake_words = wake_words or ["wall-e", "wall e", "eva", "robot"]
            for word in wake_words:
                if word in text.lower():
                    return word
        return None

    def inject_transcription(self, text: str):
        """Inject mock transcription for testing."""
        self.mock_transcriptions.append(text)

    def set_vad(self, is_speech: bool):
        self.mock_vad = is_speech
        asyncio.create_task(self._notify_vad(is_speech))