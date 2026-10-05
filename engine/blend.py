"""Paste swapped faces back with an optional XSeg occlusion mask.

InsightFace's paste_back blends the whole aligned crop. Hands in front of the face
then turn translucent, and hair the generator invents above the forehead covers the
real forehead. XSeg marks which pixels are face; running it on both the real crop
(hands, objects) and the generated crop (invented hair) and intersecting the two keeps
everything that is not shared face skin from the original frame.
"""
import cv2
import numpy as np

XSEG_SIZE = 256


def _box_mask(size):
    # Matches InsightFace 0.7.3: erode ~10% of the crop, then feather the edge.
    mask = np.zeros((size, size), np.float32)
    border = max(size // 10, 1)
    mask[border:size - border, border:size - border] = 1
    k = max(size // 20, 5)
    return cv2.GaussianBlur(mask, (2 * k + 1, 2 * k + 1), 0)


class Occluder:
    def __init__(self, session):
        self.session = session
        self.input = session.get_inputs()[0].name

    def mask(self, frame, M, fake):
        """Face probability in crop space (same size as fake), 1 = paste."""
        size = fake.shape[0]
        scale = XSEG_SIZE / size
        real = cv2.warpAffine(frame, M * scale, (XSEG_SIZE, XSEG_SIZE), borderValue=0.0)
        made = cv2.resize(fake, (XSEG_SIZE, XSEG_SIZE), interpolation=cv2.INTER_CUBIC)
        batch = np.stack([real, made]).astype(np.float32) / 255
        probs = self.session.run(None, {self.input: batch})[0][..., 0]
        masks = []
        for prob in probs:
            # Soften speckle, then stretch so confident face pixels reach 1.
            prob = cv2.GaussianBlur(prob.clip(0, 1), (0, 0), 5)
            masks.append((prob.clip(0.5, 1) - 0.5) * 2)
        combined = masks[0] * masks[1]
        return cv2.resize(combined, (size, size), interpolation=cv2.INTER_AREA)


class Blender:
    def __init__(self, occluder=None):
        self.occluder = occluder
        self.boxes = {}

    def paste(self, frame, fake, M):
        size = fake.shape[0]
        if size not in self.boxes:
            self.boxes[size] = _box_mask(size)
        mask = self.boxes[size]
        if self.occluder is not None:
            mask = mask * self.occluder.mask(frame, M, fake)
        # Work only inside the face's bounding box instead of warping the full frame.
        IM = cv2.invertAffineTransform(M)
        corners = np.array([[0, 0, 1], [size, 0, 1], [0, size, 1], [size, size, 1]], np.float32) @ IM.T
        h, w = frame.shape[:2]
        x0, y0 = np.floor(corners.min(axis=0)).astype(int)
        x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        if x1 <= x0 or y1 <= y0:
            return frame
        IM[:, 2] -= (x0, y0)
        roi = (x1 - x0, y1 - y0)
        fake_roi = cv2.warpAffine(fake, IM, roi, borderValue=0.0).astype(np.float32)
        alpha = cv2.warpAffine(mask, IM, roi, borderValue=0.0)[..., None]
        out = frame.copy()
        region = out[y0:y1, x0:x1].astype(np.float32)
        out[y0:y1, x0:x1] = (alpha * fake_roi + (1 - alpha) * region).astype(np.uint8)
        return out
