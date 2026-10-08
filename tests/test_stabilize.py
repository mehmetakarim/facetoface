import unittest

import numpy as np

from engine.stabilize import Stabilizer


class Face:
    def __init__(self, x, kps_offset=0.0):
        self.bbox = np.array([x, 100, x + 100, 220], np.float32)
        base = np.array([[30, 40], [70, 40], [50, 60], [35, 85], [65, 85]], np.float32)
        self.kps = base + [x, 100] + kps_offset


class StabilizerTests(unittest.TestCase):
    def test_jitter_of_a_still_face_is_damped(self):
        stabilizer = Stabilizer()
        stabilizer.landmarks([Face(100)])
        jittery = Face(100, kps_offset=1.0)  # 1 px wobble on a 100 px face
        stabilizer.landmarks([jittery])
        self.assertLess(float(np.abs(jittery.kps - Face(100).kps).max()), 0.5)

    def test_a_moving_face_is_not_held_back(self):
        stabilizer = Stabilizer()
        stabilizer.landmarks([Face(100)])
        moved = Face(110)  # 10 % of the face width in one frame
        expected = moved.kps.copy()
        stabilizer.landmarks([moved])
        np.testing.assert_allclose(moved.kps, expected)

    def test_masks_are_blended_with_the_previous_frame(self):
        stabilizer = Stabilizer(mask_keep=0.5)
        first = stabilizer.landmarks([Face(100)])[0]
        stabilizer.mask(first, np.ones((4, 4), np.float32))
        second = stabilizer.landmarks([Face(100)])[0]
        np.testing.assert_allclose(stabilizer.mask(second, np.zeros((4, 4), np.float32)), 0.5)

    def test_a_new_face_starts_fresh(self):
        stabilizer = Stabilizer()
        stabilizer.landmarks([Face(100)])
        far = Face(600)
        expected = far.kps.copy()
        state = stabilizer.landmarks([far])[0]
        np.testing.assert_allclose(far.kps, expected)
        np.testing.assert_allclose(stabilizer.mask(state, np.zeros((2, 2), np.float32)), 0)


if __name__ == '__main__':
    unittest.main()
