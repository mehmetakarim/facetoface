"""Publish complete results atomically without overwriting existing files."""
import os
import shutil
import tempfile
from pathlib import Path


def publish(destination, *, data=None, source=None):
    destination = Path(destination)
    staging = Path(os.environ.get('DLC_JOB_DIR', destination.parent))
    # Hard linking requires the staging file and destination to share a volume.
    if staging.stat().st_dev != destination.parent.stat().st_dev:
        staging = destination.parent
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.result-', dir=staging, delete=False) as stream:
            temporary = Path(stream.name)
            if source is not None:
                with open(source, 'rb') as original:
                    shutil.copyfileobj(original, stream)
            else:
                stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Unlike rename/replace, link fails atomically if destination already exists.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
