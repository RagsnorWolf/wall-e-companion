"""Core package — Wall-E Companion Software."""

from core.hardware import get_hardware_config, HardwareConfig, ServoConfig, MoodPose
from core.serial_comm import SerialComm, MockSerialComm, RobotState, CommandResponse
from core.state_machine import StateMachine, RobotMode, Mood, StateContext
from core.personality import PersonalityEngine, PersonalityProfile, PersonalityTrait, Memory

__all__ = [
    "get_hardware_config",
    "HardwareConfig",
    "ServoConfig",
    "MoodPose",
    "SerialComm",
    "MockSerialComm",
    "RobotState",
    "CommandResponse",
    "StateMachine",
    "RobotMode",
    "Mood",
    "StateContext",
    "PersonalityEngine",
    "PersonalityProfile",
    "PersonalityTrait",
    "Memory",
]