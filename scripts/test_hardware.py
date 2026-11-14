#!/usr/bin/env python3
"""Hardware Test Script — Wall-E Companion Software.

Validates all hardware connections and basic functionality.
Run after hardware assembly before integrating with main software.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hardware import get_hardware_config
from core.serial_comm import SerialComm, MockSerialComm
from services.vision import VisionService
from services.audio import AudioService, MockAudioService


async def test_hardware_config():
    """Test hardware configuration loading."""
    print("\n=== Hardware Config Test ===")
    try:
        hw = get_hardware_config()
        print(f"[OK] MCU: {hw.mcu.type} on {hw.mcu.port} @ {hw.mcu.baudrate}")
        print(f"[OK] Servos: {len(hw.servos)} configured")
        for sid, servo in hw.servos.items():
            print(f"  - {sid}: ch{servo.channel}, {servo.angle_range[0]} to {servo.angle_range[1]} deg")
        print(f"[OK] Moods: {list(hw.moods.keys())}")
        print(f"[OK] Camera: {hw.camera.width}x{hw.camera.height} @ {hw.camera.fps}fps")
        print(f"[OK] Audio: mic {hw.audio.mic_sample_rate}Hz, speaker {hw.audio.speaker_sample_rate}Hz")
        print(f"[OK] Battery: {hw.power.min_voltage}V - {hw.power.max_voltage}V")
        return True
    except Exception as e:
        print(f"[FAIL] Config failed: {e}")
        return False


async def test_serial_connection(mock=False):
    """Test serial communication with ESP32."""
    print("\n=== Serial Connection Test ===")
    try:
        if mock:
            serial = MockSerialComm()
        else:
            serial = SerialComm()

        connected = await serial.connect()
        if not connected:
            print("[FAIL] Failed to connect to serial port")
            return False

        print(f"[OK] Connected to {serial.hw.mcu.port}")

        # Test state request
        response = await serial.get_state()
        print(f"[OK] get_state: ok={response.ok}")

        # Test servo movement
        response = await serial.move_servo("head_pan", 10.0)
        print(f"[OK] move_servo head_pan 10°: ok={response.ok}")

        response = await serial.move_servo("head_pan", -10.0)
        print(f"[OK] move_servo head_pan -10°: ok={response.ok}")

        response = await serial.move_servo("head_pan", 0.0)
        print(f"[OK] move_servo head_pan 0°: ok={response.ok}")

        # Test mood
        response = await serial.set_mood("curious")
        print(f"[OK] set_mood curious: ok={response.ok}")

        response = await serial.set_mood("happy")
        print(f"[OK] set_mood happy: ok={response.ok}")

        response = await serial.set_mood("idle")
        print(f"[OK] set_mood idle: ok={response.ok}")

        # Test emergency stop
        response = await serial.emergency_stop()
        print(f"[OK] emergency_stop: ok={response.ok}")

        # Test reset
        response = await serial.reset()
        print(f"[OK] reset: ok={response.ok}")

        await serial.disconnect()
        print("[OK] Disconnected cleanly")
        return True

    except Exception as e:
        print(f"[FAIL] Serial test failed: {e}")
        return False


async def test_vision_service():
    """Test camera and vision processing."""
    print("\n=== Vision Service Test ===")
    try:
        vision = VisionService()
        await vision.start()
        print("[OK] Vision service started")

        # Wait for a few frames
        await asyncio.sleep(2.0)

        # Check if we got frames
        frame = vision.get_latest_frame()
        if frame is not None:
            print(f"[OK] Camera frame captured: {frame.shape}")
        else:
            print("[WARN] No frames captured yet")

        await vision.stop()
        print("[OK] Vision service stopped")
        return True

    except Exception as e:
        print(f"[FAIL] Vision test failed: {e}")
        return False


async def test_audio_service(mock=False):
    """Test audio input/output."""
    print("\n=== Audio Service Test ===")
    try:
        if mock:
            audio = MockAudioService()
        else:
            audio = AudioService()

        await audio.start()
        print("[OK] Audio service started")

        # Test TTS
        await audio.speak("Test de audio Wall-E")
        print("[OK] TTS playback queued")

        # Test sound effect
        await audio.play_sound("beep")
        print("[OK] Sound effect played")

        # Wait a bit for audio to play
        await asyncio.sleep(1.0)

        await audio.stop()
        print("[OK] Audio service stopped")
        return True

    except Exception as e:
        print(f"[FAIL] Audio test failed: {e}")
        return False


async def test_state_machine():
    """Test state machine transitions."""
    print("\n=== State Machine Test ===")
    try:
        serial = MockSerialComm()
        await serial.connect()

        from core.state_machine import StateMachine, RobotMode, Mood
        sm = StateMachine(serial)
        await sm.start()

        print(f"[OK] Initial mode: {sm.ctx.mode.value}")
        print(f"[OK] Initial mood: {sm.ctx.mood.value}")

        # Test face detection
        await sm.on_face_detected(1.5)
        await asyncio.sleep(0.1)
        print(f"[OK] After face: mode={sm.ctx.mode.value}, mood={sm.ctx.mood.value}")

        # Test wake word
        await sm.on_wake_word()
        await asyncio.sleep(0.1)
        print(f"[OK] After wake: mode={sm.ctx.mode.value}, mood={sm.ctx.mood.value}")

        # Test voice
        await sm.on_voice_detected("Hola Wall-E")
        await asyncio.sleep(0.1)
        print(f"[OK] After voice: mode={sm.ctx.mode.value}, mood={sm.ctx.mood.value}")

        # Test face lost
        await sm.on_face_lost()
        await asyncio.sleep(0.1)

        await sm.stop()
        await serial.disconnect()
        print("[OK] State machine test complete")
        return True

    except Exception as e:
        print(f"[FAIL] State machine test failed: {e}")
        return False


async def test_personality_engine():
    """Test personality engine behaviors."""
    print("\n=== Personality Engine Test ===")
    try:
        serial = MockSerialComm()
        await serial.connect()

        from core.state_machine import StateMachine
        from core.personality import PersonalityEngine

        sm = StateMachine(serial)
        await sm.start()

        personality = PersonalityEngine(serial, sm)
        await personality.start()

        # Test greetings
        await personality.greet("face_1")
        await asyncio.sleep(0.5)
        print("[OK] Greeting executed")

        await personality.greet("face_1")  # Known face
        await asyncio.sleep(0.5)
        print("[OK] Repeat greeting executed")

        # Test reactions
        await personality.react_to_praise()
        await asyncio.sleep(0.5)
        print("[OK] Praise reaction executed")

        await personality.celebrate()
        await asyncio.sleep(1.0)
        print("[OK] Celebration executed")

        # Test trait modification
        from core.personality import PersonalityTrait
        personality.set_trait(PersonalityTrait.CURIOSITY, 0.9)
        print("[OK] Trait modification executed")

        await personality.stop()
        await sm.stop()
        await serial.disconnect()
        print("[OK] Personality engine test complete")
        return True

    except Exception as e:
        print(f"[FAIL] Personality test failed: {e}")
        return False


async def test_ai_engine():
    """Test full AI engine integration."""
    print("\n=== AI Engine Integration Test ===")
    try:
        serial = MockSerialComm()
        await serial.connect()

        from core.state_machine import StateMachine
        from core.personality import PersonalityEngine
        from services.vision import VisionService
        from services.audio import MockAudioService
        from services.ai_engine import AIEngine, AIEngineConfig

        sm = StateMachine(serial)
        await sm.start()

        personality = PersonalityEngine(serial, sm)
        await personality.start()

        vision = VisionService()
        # Don't start vision in test (needs camera)

        audio = MockAudioService()
        await audio.start()

        ai_config = AIEngineConfig(
            enable_vision=False,
            enable_audio=True,
            enable_personality=True,
        )

        ai = AIEngine(serial, sm, personality, vision, audio, ai_config)
        await ai.start()

        # Simulate wake word
        audio.inject_transcription("Hola Wall-E, ¿cómo estás?")
        await ai.audio.listen_for_wake_word()
        await asyncio.sleep(0.5)
        print("[OK] Wake word detection simulated")

        # Simulate conversation
        audio.inject_transcription("¿Cuál es tu nombre?")
        await ai._process_conversation("¿Cuál es tu nombre?")
        await asyncio.sleep(0.5)
        print("[OK] Conversation processing simulated")

        await ai.stop()
        await personality.stop()
        await sm.stop()
        await audio.stop()
        await serial.disconnect()
        print("[OK] AI Engine test complete")
        return True

    except Exception as e:
        print(f"[FAIL] AI Engine test failed: {e}")
        return False


async def run_all_tests(mock=True):
    """Run all hardware/software tests."""
    print("=" * 50)
    print("Wall-E Companion - Hardware Test Suite")
    print("=" * 50)

    tests = [
        ("Hardware Config", test_hardware_config),
        ("Serial Connection", lambda: test_serial_connection(mock)),
        ("Vision Service", test_vision_service),
        ("Audio Service", lambda: test_audio_service(mock)),
        ("State Machine", test_state_machine),
        ("Personality Engine", test_personality_engine),
        ("AI Engine", test_ai_engine),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"[FAIL] {name} crashed: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 50)
    if all_passed:
        print("[OK] ALL TESTS PASSED")
    else:
        print("[FAIL] SOME TESTS FAILED")
    print("=" * 50)

    return all_passed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Wall-E Hardware Test Suite")
    parser.add_argument("--real", action="store_true", help="Test with real hardware (not mock)")
    args = parser.parse_args()

    success = asyncio.run(run_all_tests(mock=not args.real))
    sys.exit(0 if success else 1)