"""Vision Service — Wall-E Companion Software.

Camera capture, face detection, object detection, emotion recognition.
Runs in separate thread/process for performance.
"""

from __future__ import annotations

import asyncio
import cv2
import numpy as np
import time
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, List
from loguru import logger
from core.hardware import get_hardware_config


@dataclass
class Detection:
    """Single detection result."""
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, w, h
    center: tuple[int, int]


@dataclass
class FaceDetection(Detection):
    """Face detection with landmarks."""
    landmarks: Optional[np.ndarray] = None  # 68 points
    emotion: Optional[str] = None
    emotion_confidence: float = 0.0
    face_id: Optional[str] = None


@dataclass
class VisionFrame:
    """Processed frame with all detections."""
    timestamp: float
    frame: np.ndarray
    faces: List[FaceDetection]
    objects: List[Detection]
    fps: float


class VisionService:
    """Camera and vision processing service."""

    def __init__(self, config_path: Optional[str] = None):
        self.hw = get_hardware_config(config_path)
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.capture_task: Optional[asyncio.Task] = None
        self.process_task: Optional[asyncio.Task] = None

        # Detection models (lazy loaded)
        self.face_cascade: Optional[cv2.CascadeClassifier] = None
        self.face_net: Optional[cv2.dnn.Net] = None
        self.object_net: Optional[cv2.dnn.Net] = None
        self.emotion_net: Optional[cv2.dnn.Net] = None

        # Callbacks
        self.frame_callbacks: List[Callable[[VisionFrame], Awaitable[None]]] = []
        self.face_callbacks: List[Callable[[List[FaceDetection]], Awaitable[None]]] = []
        self.object_callbacks: List[Callable[[List[Detection]], Awaitable[None]]] = []

        # Performance
        self.last_fps_time = time.time()
        self.frame_count = 0
        self.current_fps = 0.0

        # Face tracking
        self.known_faces: dict = {}  # Simple tracking by position
        self.next_face_id = 0

    async def start(self):
        """Initialize camera and models."""
        await self._init_camera()
        await self._init_models()

        self.running = True
        self.capture_task = asyncio.create_task(self._capture_loop())
        self.process_task = asyncio.create_task(self._process_loop())
        logger.info("Vision service started")

    async def stop(self):
        """Stop camera and tasks."""
        self.running = False

        for task in (self.capture_task, self.process_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self.cap:
            self.cap.release()
            self.cap = None

        logger.info("Vision service stopped")

    async def _init_camera(self):
        """Initialize camera capture."""
        cam = self.hw.camera

        def open_camera():
            cap = cv2.VideoCapture(cam.device_index, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else 0)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.height)
            cap.set(cv2.CAP_PROP_FPS, cam.fps)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cam.format))
            if cam.auto_exposure:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            if cam.auto_white_balance:
                cap.set(cv2.CAP_PROP_AUTO_WB, 1)
            return cap

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        self.cap = await loop.run_in_executor(None, open_camera)

        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open camera index {cam.device_index}")

        # Verify actual settings
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        logger.info(f"Camera opened: {actual_w}x{actual_h} @ {actual_fps:.1f}fps")

    async def _init_models(self):
        """Load detection models (OpenCV DNN)."""
        models = self.hw.models

        def load_models():
            # Face detection (YuNet or Haar fallback)
            try:
                face_net = cv2.dnn.readNetFromONNX(models.vision_face_model)
                logger.info("Loaded YuNet face detection model")
            except Exception:
                face_net = None
                logger.warning("YuNet model not found, using Haar cascade")

            # Face cascade (fallback)
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )

            # Object detection (YOLOv8 ONNX)
            try:
                object_net = cv2.dnn.readNetFromONNX(models.vision_detection_model)
                logger.info("Loaded YOLOv8 object detection model")
            except Exception:
                object_net = None
                logger.warning("YOLOv8 model not found")

            # Emotion detection
            try:
                emotion_net = cv2.dnn.readNetFromONNX(models.vision_emotion_model)
                logger.info("Loaded emotion detection model")
            except Exception:
                emotion_net = None
                logger.warning("Emotion model not found")

            return face_cascade, face_net, object_net, emotion_net

        loop = asyncio.get_event_loop()
        self.face_cascade, self.face_net, self.object_net, self.emotion_net = \
            await loop.run_in_executor(None, load_models)

    async def _capture_loop(self):
        """Continuous frame capture."""
        while self.running and self.cap:
            try:
                ret, frame = await asyncio.get_event_loop().run_in_executor(
                    None, self.cap.read
                )
                if not ret:
                    await asyncio.sleep(0.01)
                    continue

                # Put frame in queue for processing
                if not hasattr(self, '_frame_queue'):
                    self._frame_queue = asyncio.Queue(maxsize=2)

                try:
                    self._frame_queue.put_nowait(frame)
                except asyncio.QueueFull:
                    pass  # Drop frame if processing can't keep up

            except Exception as e:
                logger.error(f"Capture error: {e}")
                await asyncio.sleep(0.1)

    async def _process_loop(self):
        """Process frames for detections."""
        while self.running:
            try:
                if not hasattr(self, '_frame_queue'):
                    await asyncio.sleep(0.01)
                    continue

                frame = await self._frame_queue.get()
                await self._process_frame(frame)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Process error: {e}")
                await asyncio.sleep(0.1)

    async def _process_frame(self, frame: np.ndarray):
        """Run all detections on a frame."""
        start_time = time.time()

        # Face detection
        faces = await self._detect_faces(frame)

        # Object detection
        objects = await self._detect_objects(frame)

        # Calculate FPS
        self.frame_count += 1
        if time.time() - self.last_fps_time >= 1.0:
            self.current_fps = self.frame_count / (time.time() - self.last_fps_time)
            self.frame_count = 0
            self.last_fps_time = time.time()

        vision_frame = VisionFrame(
            timestamp=time.time(),
            frame=frame,
            faces=faces,
            objects=objects,
            fps=self.current_fps,
        )

        # Notify callbacks
        for cb in self.frame_callbacks:
            try:
                await cb(vision_frame)
            except Exception as e:
                logger.error(f"Frame callback error: {e}")

        if faces:
            for cb in self.face_callbacks:
                try:
                    await cb(faces)
                except Exception as e:
                    logger.error(f"Face callback error: {e}")

        if objects:
            for cb in self.object_callbacks:
                try:
                    await cb(objects)
                except Exception as e:
                    logger.error(f"Object callback error: {e}")

    async def _detect_faces(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces using YuNet or Haar cascade."""
        faces = []
        h, w = frame.shape[:2]

        if self.face_net is not None:
            # YuNet face detection (ONNX)
            blob = cv2.dnn.blobFromImage(frame, 1.0, (320, 320), (104, 117, 123), False, False)
            self.face_net.setInput(blob)
            detections = self.face_net.forward()

            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                if confidence > 0.6:
                    x1 = int(detections[0, 0, i, 3] * w)
                    y1 = int(detections[0, 0, i, 4] * h)
                    x2 = int(detections[0, 0, i, 5] * w)
                    y2 = int(detections[0, 0, i, 6] * h)

                    face_w = x2 - x1
                    face_h = y2 - y1
                    center = (x1 + face_w // 2, y1 + face_h // 2)

                    # Extract face ROI for emotion
                    face_roi = frame[y1:y2, x1:x2]
                    emotion, emo_conf = await self._detect_emotion(face_roi)

                    # Simple face ID assignment (by position tracking)
                    face_id = self._assign_face_id(center)

                    faces.append(FaceDetection(
                        label="face",
                        confidence=float(confidence),
                        bbox=(x1, y1, face_w, face_h),
                        center=center,
                        emotion=emotion,
                        emotion_confidence=emo_conf,
                        face_id=face_id,
                    ))

        elif self.face_cascade is not None:
            # Haar cascade fallback
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )

            for (x, y, w, h) in detections:
                center = (x + w // 2, y + h // 2)
                face_roi = frame[y:y+h, x:x+w]
                emotion, emo_conf = await self._detect_emotion(face_roi)
                face_id = self._assign_face_id(center)

                faces.append(FaceDetection(
                    label="face",
                    confidence=0.8,
                    bbox=(x, y, w, h),
                    center=center,
                    emotion=emotion,
                    emotion_confidence=emo_conf,
                    face_id=face_id,
                ))

        return faces

    async def _detect_objects(self, frame: np.ndarray) -> List[Detection]:
        """Detect objects using YOLOv8."""
        objects = []

        if self.object_net is None:
            return objects

        h, w = frame.shape[:2]

        def run_yolo():
            blob = cv2.dnn.blobFromImage(frame, 1/255.0, (640, 640), swapRB=True, crop=False)
            self.object_net.setInput(blob)
            outputs = self.object_net.forward()
            return outputs

        loop = asyncio.get_event_loop()
        outputs = await loop.run_in_executor(None, run_yolo)

        # Parse YOLOv8 output
        for detection in outputs[0]:
            confidence = detection[4]
            if confidence > 0.5:
                class_scores = detection[5:]
                class_id = np.argmax(class_scores)
                class_confidence = class_scores[class_id]

                if class_confidence > 0.5:
                    cx, cy, cw, ch = detection[:4]
                    x1 = int((cx - cw/2) * w)
                    y1 = int((cy - ch/2) * h)
                    x2 = int((cx + cw/2) * w)
                    y2 = int((cy + ch/2) * h)

                    # COCO class names (subset)
                    class_names = [
                        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
                        "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear",
                        "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase",
                        "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat",
                        "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
                        "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
                        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut",
                        "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
                        "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
                        "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
                        "scissors", "teddy bear", "hair drier", "toothbrush"
                    ]

                    label = class_names[class_id] if class_id < len(class_names) else f"class_{class_id}"

                    objects.append(Detection(
                        label=label,
                        confidence=float(class_confidence),
                        bbox=(x1, y1, x2-x1, y2-y1),
                        center=(int(cx*w), int(cy*h)),
                    ))

        return objects

    async def _detect_emotion(self, face_roi: np.ndarray) -> tuple[Optional[str], float]:
        """Detect emotion from face ROI."""
        if self.emotion_net is None or face_roi.size == 0:
            return None, 0.0

        try:
            def run_emotion():
                face_resized = cv2.resize(face_roi, (64, 64))
                face_gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)
                face_normalized = face_gray.astype(np.float32) / 255.0
                blob = cv2.dnn.blobFromImage(face_normalized, 1.0, (64, 64), (0, 0, 0), False, False)
                self.emotion_net.setInput(blob)
                return self.emotion_net.forward()

            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, run_emotion)

            emotions = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
            idx = np.argmax(output[0])
            confidence = float(output[0][idx])

            return emotions[idx], confidence

        except Exception as e:
            logger.error(f"Emotion detection error: {e}")
            return None, 0.0

    def _assign_face_id(self, center: tuple[int, int]) -> str:
        """Simple face tracking by position proximity."""
        min_dist = float('inf')
        matched_id = None

        for face_id, data in self.known_faces.items():
            dist = np.sqrt((center[0] - data['center'][0])**2 + (center[1] - data['center'][1])**2)
            if dist < min_dist and dist < 100:  # 100px threshold
                min_dist = dist
                matched_id = face_id

        if matched_id:
            self.known_faces[matched_id]['center'] = center
            self.known_faces[matched_id]['last_seen'] = time.time()
            return matched_id
        else:
            face_id = f"face_{self.next_face_id}"
            self.next_face_id += 1
            self.known_faces[face_id] = {'center': center, 'last_seen': time.time()}
            return face_id

    def on_frame(self, callback: Callable[[VisionFrame], Awaitable[None]]):
        self.frame_callbacks.append(callback)

    def on_faces(self, callback: Callable[[List[FaceDetection]], Awaitable[None]]):
        self.face_callbacks.append(callback)

    def on_objects(self, callback: Callable[[List[Detection]], Awaitable[None]]):
        self.object_callbacks.append(callback)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Get latest raw frame for streaming."""
        if hasattr(self, '_frame_queue') and not self._frame_queue.empty():
            try:
                return self._frame_queue._queue[-1]
            except Exception:
                pass
        return None