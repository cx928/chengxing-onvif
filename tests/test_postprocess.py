"""单元测试：检测后处理与 NMS。"""

from __future__ import annotations

import unittest

import numpy as np

from cxonvif.detect.postprocess import decode_detections, nms
from cxonvif.detect.types import Detection

LABELS = ("person", "car", "dog")
CLASS_MAP = {"person": "person", "car": "vehicle", "dog": "animal"}


def make_dense(count: int, nc: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    data = np.zeros((1, 4 + nc, count), dtype=np.float32)
    data[0, 0] = rng.uniform(100, 500, count)
    data[0, 1] = rng.uniform(100, 500, count)
    data[0, 2] = 80
    data[0, 3] = 120
    for class_id in range(nc):
        data[0, 4 + class_id] = 0.1
    data[0, 4] = 0.9
    return data


class PostprocessTests(unittest.TestCase):
    def test_nms(self) -> None:
        boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float32)
        scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        keep = nms(boxes, scores, 0.5)
        self.assertEqual(keep, [0, 2])

    def test_decode_yolov8_layout(self) -> None:
        output = make_dense(5, 3)
        detections = decode_detections(
            output,
            labels=LABELS,
            class_map=CLASS_MAP,
            conf_threshold=0.4,
            iou_threshold=0.5,
            input_size=640,
        )
        self.assertTrue(detections)
        self.assertTrue(all(d.label == "person" for d in detections))
        self.assertTrue(all(d.group == "person" for d in detections))
        for detection in detections:
            x1, y1, x2, y2 = detection.box
            self.assertTrue(0 <= x1 <= 1 and 0 <= y1 <= 1)
            self.assertLess(x1, x2)

    def test_decode_yolov5_layout(self) -> None:
        rng = np.random.default_rng(2)
        rows = np.zeros((1, 6, 5 + 3), dtype=np.float32)
        rows[0, :, 0] = rng.uniform(100, 400, 6)
        rows[0, :, 1] = rng.uniform(100, 400, 6)
        rows[0, :, 2] = 100
        rows[0, :, 3] = 140
        rows[0, :, 4] = 0.9
        rows[0, :, 5] = 0.95  # person
        detections = decode_detections(
            rows, labels=LABELS, class_map=CLASS_MAP,
            conf_threshold=0.3, output_format="yolo_v5", input_size=640,
        )
        self.assertTrue(detections)
        self.assertEqual(detections[0].label, "person")

    def test_decode_end2end(self) -> None:
        output = np.array([[[10.0, 20.0, 110.0, 220.0, 0.95, 0.0]]], dtype=np.float32)
        detections = decode_detections(
            output,
            labels=LABELS,
            class_map=CLASS_MAP,
            conf_threshold=0.4,
            input_size=640,
            output_format="end2end",
            original_size=(640, 640),
            scale=1.0,
            pad=(0, 0),
        )
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "person")
        self.assertAlmostEqual(detections[0].box[0], 10 / 640, places=4)

    def test_decode_rtdetr_normalized(self) -> None:
        output = np.zeros((1, 2, 4 + 3), dtype=np.float32)
        output[0, 0, :4] = [0.5, 0.5, 0.2, 0.4]
        output[0, 0, 4 + 1] = 0.88  # car
        detections = decode_detections(
            output, labels=LABELS, class_map=CLASS_MAP,
            conf_threshold=0.3, output_format="rtdetr",
        )
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "car")
        self.assertEqual(detections[0].group, "vehicle")

    def test_iou(self) -> None:
        a = Detection(label="person", confidence=0.9, box=(0, 0, 10, 10))
        b = Detection(label="person", confidence=0.8, box=(5, 0, 15, 10))
        self.assertAlmostEqual(a.iou(b), 1 / 3, places=4)


if __name__ == "__main__":
    unittest.main()
