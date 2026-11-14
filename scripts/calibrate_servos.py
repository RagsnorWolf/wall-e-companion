#!/usr/bin/env python3
"""Servo Calibration Tool — Wall-E Companion Software.

Interactive calibration for each servo: find min/max pulse for 0° and max angle.
Run with hardware connected.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hardware import get_hardware_config
from core.serial_comm import SerialComm
from loguru import logger


async def calibrate_servo(serial: SerialComm, servo_id: str):
    """Interactive calibration for a single servo."""
    servo = serial.hw.get_servo(servo_id)
    if not servo:
        print(f"Unknown servo: {servo_id}")
        return

    print(f"\n{'='*50}")
    print(f"CALIBRANDO: {servo_id} (canal {servo.channel})")
    print(f"Rango actual: {servo.angle_range[0]}° a {servo.angle_range[1]}°")
    print(f"Pulso actual: {servo.min_pulse} - {servo.max_pulse}")
    print(f"{'='*50}")

    # Move to center first
    await serial.move_servo(servo_id, 0, speed=50)
    await asyncio.sleep(1)

    # Find min pulse (0° or min angle)
    print(f"\n--- Encontrando pulso MÍNIMO ({servo.angle_range[0]}°) ---")
    print("Usa 'a'/'d' para ajustar, 'w'/'s' para pasos grandes, 'enter' para confirmar")
    pulse = servo.min_pulse
    step = 10

    while True:
        await serial.move_servo(servo_id, 0, speed=50)  # Will use current pulse via calibrate
        # Send raw pulse via calibrate command
        response = await serial.calibrate(servo_id, [{"angle": servo.angle_range[0], "pulse": pulse}])
        print(f"Pulso: {pulse}  (a/d: ±{step}, w/s: ±{step*10}, enter: ok)")
        cmd = input("> ").strip().lower()
        if cmd == 'a':
            pulse -= step
        elif cmd == 'd':
            pulse += step
        elif cmd == 'w':
            pulse -= step * 10
        elif cmd == 's':
            pulse += step * 10
        elif cmd == '':
            break
        pulse = max(100, min(3000, pulse))

    min_pulse = pulse
    print(f"✓ Min pulse guardado: {min_pulse}")

    # Find max pulse (max angle)
    print(f"\n--- Encontrando pulso MÁXIMO ({servo.angle_range[1]}°) ---")
    pulse = servo.max_pulse

    while True:
        response = await serial.calibrate(servo_id, [{"angle": servo.angle_range[1], "pulse": pulse}])
        print(f"Pulso: {pulse}  (a/d: ±{step}, w/s: ±{step*10}, enter: ok)")
        cmd = input("> ").strip().lower()
        if cmd == 'a':
            pulse -= step
        elif cmd == 'd':
            pulse += step
        elif cmd == 'w':
            pulse -= step * 10
        elif cmd == 's':
            pulse += step * 10
        elif cmd == '':
            break
        pulse = max(100, min(3000, pulse))

    max_pulse = pulse
    print(f"✓ Max pulse guardado: {max_pulse}")

    # Test interpolation
    print("\n--- Probando interpolación ---")
    for angle in [servo.angle_range[0], 0, servo.angle_range[1]]:
        await serial.move_servo(servo_id, angle, speed=50)
        await asyncio.sleep(0.5)
        print(f"  {angle}° -> OK")

    # Return to center
    await serial.move_servo(servo_id, 0, speed=50)

    return {"min_pulse": min_pulse, "max_pulse": max_pulse}


async def main():
    print("Wall-E Servo Calibration Tool")
    print("==============================")

    # Connect
    serial = SerialComm()
    connected = await serial.connect()
    if not connected:
        print("Failed to connect to hardware")
        return

    print(f"Connected to {serial.hw.mcu.port}")

    # Select servos to calibrate
    servo_ids = list(serial.hw.servos.keys())
    print("\nServos disponibles:")
    for i, sid in enumerate(servo_ids):
        print(f"  {i+1}. {sid}")

    print("\nOpciones:")
    print("  - Número de servo (1-7)")
    print("  - 'all' para todos")
    print("  - 'q' para salir")

    while True:
        choice = input("\nSelecciona servo: ").strip().lower()

        if choice == 'q':
            break
        elif choice == 'all':
            results = {}
            for sid in servo_ids:
                result = await calibrate_servo(serial, sid)
                if result:
                    results[sid] = result
            # Save to config
            save_calibration(results)
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(servo_ids):
                result = await calibrate_servo(serial, servo_ids[idx])
                if result:
                    save_calibration({servo_ids[idx]: result})
            else:
                print("Número inválido")
        else:
            print("Opción inválida")

    await serial.disconnect()
    print("\nCalibración completada.")


def save_calibration(results: dict):
    """Save calibration to hardware.yaml."""
    config_path = Path(__file__).parent.parent / "config" / "hardware.yaml"

    import yaml
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    for servo_id, cal in results.items():
        for servo in config['servos']:
            if servo['id'] == servo_id:
                servo['min_pulse'] = cal['min_pulse']
                servo['max_pulse'] = cal['max_pulse']
                break

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\n✓ Calibración guardada en {config_path}")
    print("Reinicia el software para aplicar cambios.")


if __name__ == "__main__":
    asyncio.run(main())