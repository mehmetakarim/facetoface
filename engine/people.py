"""Find the people in a target and pick the faces that belong to the chosen ones.

Faces are compared by their w600k_r50 identity embeddings (L2-normalised, so the
dot product is the cosine similarity). Grouping is strict so two people are never
merged; matching during processing is looser to tolerate pose and lighting.
"""
import numpy as np

SAME_PERSON = 0.45  # scan: join an existing person only when clearly the same
MATCH = 0.30        # processing: different people typically score below ~0.2


def group(faces):
    """faces: (normed embedding, quality, thumbnail). Returns people, most seen first."""
    people = []
    for embedding, quality, thumbnail in faces:
        best, similarity = None, -1.0
        for person in people:
            score = float(person['center'] @ embedding)
            if score > similarity:
                best, similarity = person, score
        if best is not None and similarity >= SAME_PERSON:
            best['sum'] = best['sum'] + embedding
            best['center'] = best['sum'] / np.linalg.norm(best['sum'])
            best['count'] += 1
            if quality > best['quality']:
                best['quality'], best['thumbnail'] = quality, thumbnail
        else:
            people.append({'sum': embedding.copy(), 'center': embedding.copy(), 'count': 1,
                           'quality': quality, 'thumbnail': thumbnail})
    return sorted(people, key=lambda person: -person['count'])


def assign(found, selected, threshold=MATCH):
    """(face index, person index) pairs: each chosen person's best match in the frame.

    A face claimed by two chosen people goes to the one it resembles most, so two
    look-alikes never share one source.
    """
    if not len(found) or not len(selected):
        return []
    similarity = np.asarray(selected, np.float32) @ np.asarray(found, np.float32).T
    owner = {}
    for person, row in enumerate(similarity):
        face = int(row.argmax())
        if row[face] >= threshold and (face not in owner or row[face] > similarity[owner[face], face]):
            owner[face] = person
    return sorted(owner.items())


def choose(found, selected, threshold=MATCH):
    """Indices of detected faces to swap."""
    return [face for face, _ in assign(found, selected, threshold)]


def overlap(a, b):
    """Intersection over union of two (x0, y0, x1, y1) boxes."""
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    inter = width * height
    return float(inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter))


class Tracker:
    """Recognises each face once and follows it by position between frames.

    Identity embeddings cost a model run per face per frame. A face that barely
    moved since the previous frame keeps its identity (chosen person or nobody);
    it is re-checked every `refresh` frames and new faces are always recognised.
    """

    def __init__(self, selected, threshold=MATCH, refresh=15, min_overlap=0.5):
        self.selected = np.asarray(selected, np.float32)
        self.threshold, self.refresh, self.min_overlap = threshold, refresh, min_overlap
        self.tracks = []

    def reset(self):
        """Forget all positions, e.g. after a scene cut where people may jump."""
        self.tracks = []

    def assign(self, faces, embed):
        """faces have .bbox; embed(face) returns its normed embedding. Returns (face, person) pairs."""
        current, pending, taken = [], [], set()
        near = [[overlap(face.bbox, track['bbox']) for track in self.tracks] for face in faces]
        for index, face in enumerate(faces):
            best, best_overlap = None, self.min_overlap
            for number in range(len(self.tracks)):
                score = near[index][number] if number not in taken else 0.0
                if score >= best_overlap:
                    best, best_overlap = number, score
            # When people cross, boxes overlap several tracks; position alone is ambiguous.
            crowded = best is not None and (sum(v > 0.1 for v in near[index]) > 1
                                            or sum(row[best] > 0.1 for row in near) > 1)
            if best is not None and not crowded and self.tracks[best]['age'] < self.refresh:
                taken.add(best)
                track = self.tracks[best]
                current.append({**track, 'bbox': face.bbox, 'age': track['age'] + 1})
            else:
                pending.append(index)
                current.append(None)
        if pending:
            similarity = self.selected @ np.asarray([embed(faces[i]) for i in pending], np.float32).T
            for column, index in enumerate(pending):
                person = int(similarity[:, column].argmax())
                score = float(similarity[person, column])
                current[index] = {'bbox': faces[index].bbox, 'person': person if score >= self.threshold else None,
                                  'score': score, 'age': 0}
        self.tracks = current
        # One face per chosen person: the closest match wins.
        owner = {}
        for index, track in enumerate(current):
            person = track['person']
            if person is not None and (person not in owner or track['score'] > current[owner[person]]['score']):
                owner[person] = index
        return sorted((index, person) for person, index in owner.items())
