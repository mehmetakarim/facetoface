"""Temporal smoothing that stops a swapped face from shimmering between frames.

The detector's five landmarks wobble by a few pixels every frame even when the
person is still; the generated face is aligned to them, so it wobbles too. The
occlusion mask is likewise recomputed from scratch each frame. Each face is
matched to its previous-frame self by box overlap; landmarks and mask are blended
with the previous ones, strongly when still and not at all when moving fast, so
smoothing never makes the face lag behind a turning head.
"""
import numpy as np

from engine.people import overlap


def keep_previous(motion):
    """Weight of the previous landmarks for a movement of `motion` face-widths."""
    if motion < 0.015:
        return 0.7
    if motion < 0.04:
        return 0.4
    return 0.0


class Stabilizer:
    """landmarks() runs on the analysis side, mask() on the rendering side, one frame
    apart at most; each face carries its own state so the two never mix frames."""

    def __init__(self, min_overlap=0.3, mask_keep=0.5):
        self.min_overlap, self.mask_keep = min_overlap, mask_keep
        self.previous = []

    def landmarks(self, faces):
        """Smooths each face's .kps in place; returns one state per face for mask()."""
        current, taken = [], set()
        for face in faces:
            best, best_overlap = None, self.min_overlap
            for number, before in enumerate(self.previous):
                score = overlap(face.bbox, before['bbox']) if number not in taken else 0.0
                if score >= best_overlap:
                    best, best_overlap = number, score
            state = {'bbox': face.bbox, 'mask': None, 'previous': None}
            if best is not None:
                taken.add(best)
                before = self.previous[best]
                width = max(float(face.bbox[2] - face.bbox[0]), 1.0)
                motion = float(np.linalg.norm(face.kps - before['kps'], axis=1).mean()) / width
                keep = keep_previous(motion)
                face.kps = (keep * before['kps'] + (1 - keep) * face.kps).astype(np.float32)
                # Linked, not copied: the previous mask may still be rendering.
                state['previous'] = before if keep else None
            state['kps'] = face.kps.copy()
            current.append(state)
        self.previous = current
        return current

    def mask(self, state, mask):
        """Blends this frame's occlusion mask (crop space) with the face's previous one."""
        before = state['previous']['mask'] if state['previous'] is not None else None
        if before is not None and before.shape == mask.shape:
            mask = self.mask_keep * before + (1 - self.mask_keep) * mask
        state['mask'] = mask
        state['previous'] = None  # keep memory flat: only one frame of history
        return mask
