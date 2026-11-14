"""Wall-E Companion — Main Entry Point.

Initializes all services, starts the robot brain, runs the web UI.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from loguru import logger

# Core
from core.hardware import get_hardware_config
from core.serial_comm import SerialComm, MockSerialComm
from core.state_machine import StateMachine
from core.personality import PersonalityEngine

# Services
from services.vision import VisionService
from services.audio import AudioService, MockAudioService
from services.ai_engine import AIEngine, AIEngineConfig

# Web UI
from ui.web_server import create_app


class WallECompanion:
    """Main application class."""

    def __init__(self, config_path: str = None, mock: bool = False):
        self.config_path = config_path or str(
            Path(__file__).parent / "config" / "hardware.yaml"
        )
        self.mock = mock
        self.running = False

        # Components
        self.serial: SerialComm | MockSerialComm = None
        self.state_machine: StateMachine = None
        self.personality: PersonalityEngine = None
        self.vision: VisionService = None
        self.audio: AudioService | MockAudioService = None
        self.ai_engine: AIEngine = None
        self.web_app = None
        self.web_server = None

        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging."""
        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        )
        logger.add(
            "logs/wall-e_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="7 days",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        )

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing Wall-E Companion...")

        # Load hardware config
        hw = get_hardware_config(self.config_path)
        logger.info(f"Hardware config loaded: {hw.mcu.type} on {hw.mcu.port}")

        # Serial communication
        if self.mock:
            self.serial = MockSerialComm(self.config_path)
        else:
            self.serial = SerialComm(self.config_path)

        connected = await self.serial.connect()
        if not connected:
            if not self.mock:
                logger.warning("Failed to connect to hardware, falling back to mock mode")
                await self.serial.disconnect()
                self.serial = MockSerialComm(self.config_path)
                await self.serial.connect()
            else:
                raise RuntimeError("Failed to connect to mock serial")

        # State machine
        self.state_machine = StateMachine(self.serial, self.config_path)
        await self.state_machine.start()

        # Personality engine
        self.personality = PersonalityEngine(self.serial, self.state_machine, self.config_path)
        await self.personality.start()

        # Vision service
        self.vision = VisionService(self.config_path)
        try:
            await self.vision.start()
        except Exception as e:
            logger.warning(f"Vision service failed to start: {e}")
            self.vision = None

        # Audio service
        if self.mock:
            self.audio = MockAudioService(self.config_path)
        else:
            self.audio = AudioService(self.config_path)

        try:
            await self.audio.start()
        except Exception as e:
            logger.warning(f"Audio service failed to start: {e}")
            if not self.mock:
                self.audio = MockAudioService(self.config_path)
                await self.audio.start()

        # AI Engine
        ai_config = AIEngineConfig(
            enable_vision=self.vision is not None,
            enable_audio=self.audio is not None,
            enable_personality=True,
        )
        self.ai_engine = AIEngine(
            self.serial,
            self.state_machine,
            self.personality,
            self.vision,
            self.audio,
            ai_config,
            self.config_path,
        )
        await self.ai_engine.start()

        # Web UI
        self.web_app = create_app(self)
        self.running = True
        logger.info("All components initialized")

    async def start_web_server(self, host: str = "0.0.0.0", port: int = 5173):
        """Start the web UI server."""
        import uvicorn

        config = uvicorn.Config(
            self.web_app,
            host=host,
            port=port,
            log_level="info",
        )
        self.web_server = uvicorn.Server(config)
        await self.web_server.serve()

    async def run(self):
        """Run the main application."""
        self.running = True
        logger.info("Wall-E Companion running. Press Ctrl+C to stop.")

        try:
            # Run web server (blocks)
            await self.start_web_server()
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down Wall-E Companion...")
        self.running = False

        # Stop in reverse order
        if self.ai_engine:
            await self.ai_engine.stop()
        if self.personality:
            await self.personality.stop()
        if self.state_machine:
            await self.state_machine.stop()
        if self.vision:
            await self.vision.stop()
        if self.audio:
            await self.audio.stop()
        if self.serial:
            await self.serial.disconnect()

        if self.web_server:
            self.web_server.should_exit = True

        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Wall-E Companion Software")
    parser.add_argument("--config", help="Path to hardware config YAML")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no hardware)")
    parser.add_argument("--no-web", action="store_true", help="Disable web UI")
    args = parser.parse_args()

    # Ensure logs directory
    Path("logs").mkdir(exist_ok=True)

    companion = WallECompanion(config_path=args.config, mock=args.mock)

    # Handle signals
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Signal received, shutting down...")
        asyncio.create_task(companion.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await companion.initialize()

    if args.no_web:
        # Run without web UI
        logger.info("Running without web UI. Press Ctrl+C to stop.")
        try:
            while companion.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await companion.shutdown()
    else:
        await companion.run()


if __name__ == "__main__":
    asyncio.run(main())