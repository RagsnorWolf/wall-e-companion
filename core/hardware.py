"""Hardware Abstraction Layer — Wall-E Companion Software.

Loads hardware config, provides typed access to servo/camera/audio/power specs.
Single source of truth for all hardware parameters.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class ServoConfig:
    id: str
    channel: int
    min_pulse: int
    max_pulse: int
    angle_range: tuple[float, float]
    default_angle: float
    inverted: bool = False
    speed: int = 100

    def angle_to_pulse(self, angle: float) -> int:
        """Convert angle to PWM pulse width."""
        angle = max(self.angle_range[0], min(self.angle_range[1], angle))
        if self.inverted:
            angle = -angle
        ratio = (angle - self.angle_range[0]) / (self.angle_range[1] - self.angle_range[0])
        return int(self.min_pulse + ratio * (self.max_pulse - self.min_pulse))

    def pulse_to_angle(self, pulse: int) -> float:
        """Convert PWM pulse width to angle."""
        ratio = (pulse - self.min_pulse) / (self.max_pulse - self.min_pulse)
        angle = self.angle_range[0] + ratio * (self.angle_range[1] - self.angle_range[0])
        return -angle if self.inverted else angle


@dataclass
class MCUConfig:
    type: str
    port: str
    baudrate: int
    protocol: str
    timeout: float
    reconnect_interval: float


@dataclass
class CameraConfig:
    type: str
    device_index: int
    width: int
    height: int
    fps: int
    format: str
    auto_exposure: bool
    auto_white_balance: bool


@dataclass
class AudioConfig:
    mic_type: str
    mic_sample_rate: int
    mic_channels: int
    mic_chunk_size: int
    mic_device_index: Optional[int]
    speaker_type: str
    speaker_sample_rate: int
    speaker_channels: int
    speaker_chunk_size: int
    speaker_device_index: Optional[int]
    speaker_volume: float


@dataclass
class PowerConfig:
    battery_type: str
    voltage_monitor: str
    adc_pin: int
    min_voltage: float
    max_voltage: float
    low_alert_voltage: float
    critical_voltage: float
    update_interval: float

    def voltage_to_percent(self, voltage: float) -> int:
        """Convert voltage to battery percentage (0-100)."""
        if voltage >= self.max_voltage:
            return 100
        if voltage <= self.min_voltage:
            return 0
        return int((voltage - self.min_voltage) / (self.max_voltage - self.min_voltage) * 100)

    def is_low(self, voltage: float) -> bool:
        return voltage <= self.low_alert_voltage

    def is_critical(self, voltage: float) -> bool:
        return voltage <= self.critical_voltage


@dataclass
class SensorsConfig:
    tof: str
    imu: str
    temp: str
    i2c_address: int
    imu_address: int


@dataclass
class BehaviorConfig:
    idle_timeout: float
    watchdog_timeout: float
    max_servo_speed: int
    smoothing_factor: float
    enable_collision_avoidance: bool
    tof_threshold_mm: int


@dataclass
class ModelsConfig:
    whisper_model_size: str
    whisper_language: str
    whisper_device: str
    piper_voice: str
    piper_length_scale: float
    piper_noise_scale: float
    piper_noise_w: float
    vision_detection_model: str
    vision_emotion_model: str
    vision_face_model: str


@dataclass
class WebUIConfig:
    host: str
    port: int
    ws_port: int
    cors_origins: list[str]


@dataclass
class MoodPose:
    head_pan: float
    head_tilt: float
    eye_L: float
    eye_R: float
    body_lean: float
    arm_L: float
    arm_R: float

    def to_dict(self) -> dict[str, float]:
        return {
            "head_pan": self.head_pan,
            "head_tilt": self.head_tilt,
            "eye_L": self.eye_L,
            "eye_R": self.eye_R,
            "body_lean": self.body_lean,
            "arm_L": self.arm_L,
            "arm_R": self.arm_R,
        }


class HardwareConfig:
    """Singleton hardware configuration manager."""

    _instance: Optional[HardwareConfig] = None

    def __new__(cls, config_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        if self._initialized:
            return
        self._initialized = True

        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "hardware.yaml"

        self.config_path = Path(config_path)
        self._load()

    def _load(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # MCU
        mcu = data["mcu"]
        self.mcu = MCUConfig(
            type=mcu["type"],
            port=mcu["port"],
            baudrate=mcu["baudrate"],
            protocol=mcu["protocol"],
            timeout=mcu.get("timeout", 1.0),
            reconnect_interval=mcu.get("reconnect_interval", 5.0),
        )

        # Servos
        self.servos: dict[str, ServoConfig] = {}
        for s in data["servos"]:
            self.servos[s["id"]] = ServoConfig(
                id=s["id"],
                channel=s["channel"],
                min_pulse=s["min_pulse"],
                max_pulse=s["max_pulse"],
                angle_range=tuple(s["angle_range"]),
                default_angle=s["default_angle"],
                inverted=s.get("inverted", False),
                speed=s.get("speed", 100),
            )

        # Mood poses
        self.moods: dict[str, MoodPose] = {}
        for mood_name, pose in data["moods"].items():
            self.moods[mood_name] = MoodPose(**pose)

        # Camera
        cam = data["camera"]
        self.camera = CameraConfig(
            type=cam["type"],
            device_index=cam["device_index"],
            width=cam["width"],
            height=cam["height"],
            fps=cam["fps"],
            format=cam.get("format", "MJPG"),
            auto_exposure=cam.get("auto_exposure", True),
            auto_white_balance=cam.get("auto_white_balance", True),
        )

        # Audio
        aud = data["audio"]
        self.audio = AudioConfig(
            mic_type=aud["mic"]["type"],
            mic_sample_rate=aud["mic"]["sample_rate"],
            mic_channels=aud["mic"]["channels"],
            mic_chunk_size=aud["mic"].get("chunk_size", 1024),
            mic_device_index=aud["mic"].get("device_index"),
            speaker_type=aud["speaker"]["type"],
            speaker_sample_rate=aud["speaker"]["sample_rate"],
            speaker_channels=aud["speaker"]["channels"],
            speaker_chunk_size=aud["speaker"].get("chunk_size", 1024),
            speaker_device_index=aud["speaker"].get("device_index"),
            speaker_volume=aud["speaker"].get("volume", 0.8),
        )

        # Power
        pwr = data["power"]
        self.power = PowerConfig(
            battery_type=pwr["battery_type"],
            voltage_monitor=pwr["voltage_monitor"],
            adc_pin=pwr.get("adc_pin", 4),
            min_voltage=pwr["min_voltage"],
            max_voltage=pwr["max_voltage"],
            low_alert_voltage=pwr["low_alert_voltage"],
            critical_voltage=pwr["critical_voltage"],
            update_interval=pwr.get("update_interval", 1.0),
        )

        # Sensors
        sen = data["sensors"]
        self.sensors = SensorsConfig(
            tof=sen["tof"],
            imu=sen["imu"],
            temp=sen["temp"],
            i2c_address=sen.get("i2c_address", 0x29),
            imu_address=sen.get("imu_address", 0x68),
        )

        # Behavior
        beh = data["behavior"]
        self.behavior = BehaviorConfig(
            idle_timeout=beh["idle_timeout"],
            watchdog_timeout=beh["watchdog_timeout"],
            max_servo_speed=beh["max_servo_speed"],
            smoothing_factor=beh["smoothing_factor"],
            enable_collision_avoidance=beh["enable_collision_avoidance"],
            tof_threshold_mm=beh["tof_threshold_mm"],
        )

        # Models
        mod = data["models"]
        self.models = ModelsConfig(
            whisper_model_size=mod["whisper"]["model_size"],
            whisper_language=mod["whisper"]["language"],
            whisper_device=mod["whisper"]["device"],
            piper_voice=mod["piper_tts"]["voice"],
            piper_length_scale=mod["piper_tts"]["length_scale"],
            piper_noise_scale=mod["piper_tts"]["noise_scale"],
            piper_noise_w=mod["piper_tts"]["noise_w"],
            vision_detection_model=mod["vision"]["detection_model"],
            vision_emotion_model=mod["vision"]["emotion_model"],
            vision_face_model=mod["vision"]["face_model"],
        )

        # Web UI
        ui = data["web_ui"]
        self.web_ui = WebUIConfig(
            host=ui["host"],
            port=ui["port"],
            ws_port=ui["ws_port"],
            cors_origins=ui.get("cors_origins", ["*"]),
        )

        logger.info(f"Hardware config loaded from {self.config_path}")

    def get_servo(self, servo_id: str) -> Optional[ServoConfig]:
        return self.servos.get(servo_id)

    def get_mood(self, mood_name: str) -> Optional[MoodPose]:
        return self.moods.get(mood_name)

    def reload(self):
        """Reload configuration from file."""
        self._load()


# Global instance getter
def get_hardware_config(config_path: Optional[str] = None) -> HardwareConfig:
    return HardwareConfig(config_path)