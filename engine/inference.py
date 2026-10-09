"""Load only InsightFace's inference modules in an isolated package namespace.

InsightFace 0.7.3 eagerly imports its optional 3D renderer from its root/app
packages. That renderer imports pyplot and scans all system fonts, even for
headless inference. We reuse the installed, unmodified inference code under a
private namespace so neither package initializer nor the renderer is executed.
This adapter is intentionally restricted to the pinned InsightFace version.
"""
from importlib import import_module, metadata, util
from importlib.machinery import ModuleSpec
from pathlib import Path
import sys
from types import ModuleType


def _namespace(name, directory):
    if name in sys.modules:
        return
    module = ModuleType(name)
    module.__package__ = name
    module.__path__ = [str(directory)]
    module.__spec__ = ModuleSpec(name, loader=None, is_package=True)
    module.__spec__.submodule_search_locations = module.__path__
    sys.modules[name] = module


def load_inference():
    if metadata.version('insightface') != '0.7.3':
        raise ValueError('Bu motor InsightFace 0.7.3 sürümünü gerektirir. Proje bağımlılıklarını yeniden kurun.')
    spec = util.find_spec('insightface')
    if spec is None or not spec.origin:
        raise ValueError('Yüz işleme kitaplığı bulunamadı. Proje bağımlılıklarını yeniden kurun.')
    root = Path(spec.origin).parent
    prefix = 'engine._insightface_inference'
    _namespace(prefix, root)
    _namespace(prefix + '.app', root / 'app')
    models = import_module(prefix + '.model_zoo.model_zoo')
    common = import_module(prefix + '.app.common')
    def get_model(path, **options):
        # The public 0.7.3 get_model drops sess_options. Bypass that convenience
        # function so thread limits and DirectML session settings reach ORT.
        if not Path(path).is_file():
            raise ValueError('Model dosyası bulunamadı.')
        return models.ModelRouter(str(path)).get_model(**options)

    return get_model, common.Face
