import tempfile
import unittest
from pathlib import Path

import numpy as np

from engine.people import Tracker, assign, choose, group
from engine.protocol import validate


def identity(seed, noise=0.0, base=None):
    """A unit embedding; with base, the same person seen again (cosine ~1/sqrt(1+noise²))."""
    rng = np.random.default_rng(seed)
    vector = base if base is not None else rng.standard_normal(512)
    vector = vector / np.linalg.norm(vector) + noise * rng.standard_normal(512) / np.sqrt(512)
    return (vector / np.linalg.norm(vector)).astype(np.float32)


class PeopleTests(unittest.TestCase):
    def test_two_people_are_kept_apart_and_counted(self):
        alice, bob = identity(1), identity(2)
        faces = [(identity(10 + i, 0.6, alice), 1.0, f'a{i}') for i in range(5)]
        faces += [(identity(20 + i, 0.6, bob), 2.0 if i == 1 else 1.0, f'b{i}') for i in range(3)]
        people = group(faces)
        self.assertEqual([p['count'] for p in people], [5, 3])
        self.assertEqual(people[1]['thumbnail'], 'b1')  # best quality face is shown
        self.assertGreater(float(people[0]['center'] @ alice), 0.9)

    def test_choose_swaps_only_the_selected_person_wherever_they_stand(self):
        alice, bob = identity(1), identity(2)
        frame_left = [identity(3, 0.7, alice), identity(4, 0.7, bob)]
        frame_swapped = [identity(5, 0.7, bob), identity(6, 0.7, alice)]
        self.assertEqual(choose(frame_left, [alice]), [0])
        self.assertEqual(choose(frame_swapped, [alice]), [1])
        self.assertEqual(choose(frame_swapped, [alice, bob]), [0, 1])

    def test_each_face_is_assigned_to_its_own_person(self):
        alice, bob = identity(1), identity(2)
        frame = [identity(8, 0.7, bob), identity(9, 0.7, alice)]
        self.assertEqual(assign(frame, [alice, bob]), [(0, 1), (1, 0)])

    def test_a_shared_best_match_goes_to_the_closest_person(self):
        alice = identity(1)
        twin = identity(11, 0.4, alice)  # looks like Alice, not present in the frame
        frame = [identity(12, 0.5, alice)]
        self.assertEqual(assign(frame, [twin, alice]), [(0, 1)])

    def test_absent_person_is_not_replaced_by_someone_else(self):
        alice, bob = identity(1), identity(2)
        self.assertEqual(choose([identity(7, 0.7, bob)], [alice]), [])
        self.assertEqual(choose([], [alice]), [])


class Face:
    def __init__(self, bbox, embedding):
        self.bbox, self.embedding = np.asarray(bbox, np.float32), embedding


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.alice, self.bob = identity(1), identity(2)
        self.calls = 0

    def embed(self, face):
        self.calls += 1
        return face.embedding

    def test_still_faces_are_recognised_once(self):
        tracker = Tracker([self.alice], refresh=15)
        for shift in range(10):  # both people drift a little each frame
            faces = [Face([100 + shift, 100, 200 + shift, 220], identity(3, 0.5, self.bob)),
                     Face([400 - shift, 100, 500 - shift, 220], identity(4, 0.5, self.alice))]
            self.assertEqual(tracker.assign(faces, self.embed), [(1, 0)])
        self.assertEqual(self.calls, 2)

    def test_identity_is_rechecked_after_refresh_frames(self):
        tracker = Tracker([self.alice], refresh=5)
        face = Face([100, 100, 200, 220], identity(4, 0.5, self.alice))
        for _ in range(13):
            tracker.assign([face], self.embed)
        self.assertEqual(self.calls, 3)  # frames 1, 7 and 13 recognise

    def test_people_swapping_places_are_recognised_again(self):
        tracker = Tracker([self.alice])
        left, right = [100, 100, 200, 220], [400, 100, 500, 220]
        alice, bob = identity(5, 0.5, self.alice), identity(6, 0.5, self.bob)
        self.assertEqual(tracker.assign([Face(left, alice), Face(right, bob)], self.embed), [(0, 0)])
        # An instant swap is a scene cut: the worker resets the tracker and all are recognised.
        tracker.reset()
        self.assertEqual(tracker.assign([Face(left, bob), Face(right, alice)], self.embed), [(1, 0)])

    def test_crossing_faces_are_recognised_again(self):
        tracker = Tracker([self.alice])
        alice, bob = identity(9, 0.5, self.alice), identity(10, 0.5, self.bob)
        tracker.assign([Face([100, 100, 200, 220], alice), Face([400, 100, 500, 220], bob)], self.embed)
        # Mid-crossing both boxes overlap each other's previous track: ambiguous, so re-check.
        before = self.calls
        result = tracker.assign([Face([170, 100, 270, 220], bob), Face([230, 100, 330, 220], alice)], self.embed)
        self.assertEqual(self.calls - before, 2)
        self.assertEqual(result, [(1, 0)])

    def test_a_newcomer_is_recognised_and_left_alone(self):
        tracker = Tracker([self.alice])
        alice = Face([100, 100, 200, 220], identity(7, 0.5, self.alice))
        tracker.assign([alice], self.embed)
        stranger = Face([400, 100, 500, 220], identity(8, 0.5, self.bob))
        self.assertEqual(tracker.assign([alice, stranger], self.embed), [(0, 0)])
        self.assertEqual(self.calls, 2)


class SelectionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ['kaynak.jpg', 'hedef.mp4']:
            (root / name).write_bytes(b'x')
        self.config = dict(mode='video', source=str(root / 'kaynak.jpg'), target=str(root / 'hedef.mp4'),
                           output=str(root / 'sonuc.mp4'))

    def test_target_scan_needs_only_a_target(self):
        config = {'mode': 'target_faces', 'target': self.config['target']}
        self.assertEqual(validate(config), config)
        with self.assertRaises(ValueError):
            validate({'mode': 'target_faces', 'target': self.config['source'] + '.txt'})

    def test_camera_scan_needs_a_valid_camera(self):
        self.assertEqual(validate({'mode': 'target_faces', 'camera': 1}), {'mode': 'target_faces', 'camera': 1})
        for camera in [-1, 10, '0']:
            with self.subTest(camera=camera), self.assertRaises(ValueError):
                validate({'mode': 'target_faces', 'camera': camera})

    def test_selected_embeddings_are_validated(self):
        self.assertTrue(validate({**self.config, 'target_embeddings': [[0.0] * 512]}))
        for bad in ['x', [[0.0] * 511], [['a'] * 512], [[0.0] * 512] * 9]:
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(ValueError):
                validate({**self.config, 'target_embeddings': bad})

    def test_per_person_sources_are_validated(self):
        one = {**self.config, 'target_embeddings': [[0.0] * 512, [0.0] * 512]}
        self.assertTrue(validate({**one, 'target_sources': [None, self.config['source']]}))
        for bad in [[None], [None, 'eksik.jpg'], [None, self.config['target']], 'x']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate({**one, 'target_sources': bad})


if __name__ == '__main__':
    unittest.main()
