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
