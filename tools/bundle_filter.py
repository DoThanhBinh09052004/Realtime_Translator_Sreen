"""Remove development payloads after dependency hooks have collected their data.

Keep import-time compatibility helpers (for example scipy._lib._testutils),
which are not test suites. Apply the same policy to files and PYZ modules.
"""
from pathlib import PurePosixPath


_DEV_DIRS = {'test', 'tests', 'testing', '__pycache__', 'examples', 'samples', 'docs'}
_RUNTIME_HELPERS = {
    'anyio._core._testing', 'anyio.abc._testing',
    # numpy.testing imports the pd_NA sentinel at module import time.
    'numpy._core.tests', 'numpy._core.tests._natype',
}
_UNUSED_HELPERS = {
    'numpy.ma.testutils', 'shapely.testing', 'skimage._shared.testing',
    'sklearn.utils._testing', 'scipy.linalg._testutils',
    'scipy.special._testutils', 'scipy.special._mptestutils',
}


def development_payload(name: str, *, module: bool = False) -> bool:
    """Use package-relative destinations, never names of checkout ancestors."""
    if module:
        # scipy's array_api_compat imports numpy's public namespace, including
        # this lazy assertion-helper API. Its own tests/ remain excluded.
        if name in _RUNTIME_HELPERS:
            return False
        if name == 'numpy.testing' or name.startswith('numpy.testing.'):
            return 'tests' in name.split('.') or 'test' in name.split('.')
        parts = name.lower().split('.')
        return (bool(set(parts) & _DEV_DIRS)
                or any(p.startswith('test_') or p == 'conftest' for p in parts)
                or name in _UNUSED_HELPERS
                or name == 'PyQt5.QtTest'
                or name.startswith('sklearn.utils._test_common'))
    path = PurePosixPath(name.replace('\\', '/'))
    parts = [p.lower() for p in path.parts]
    filename = parts[-1] if parts else ''
    # These bundled datasets are demonstration images/tabular training examples,
    # not OCR dictionaries or model weights. Do not match generic data/ folders.
    normalized = '/'.join(parts).removeprefix('_internal/')
    python_module = normalized.removesuffix('.py').replace('/', '.')
    unused_test_binary = (normalized.startswith('scipy/')
                          and (filename.startswith('_test_')
                               or filename.startswith(('_ctest.', '_cytest.'))))
    qt_development = (normalized.startswith(('pyqt5/bindings/', 'pyqt5/qt5/qml/qttest/'))
                      or filename in {'qttest.pyd', 'qt5test.dll', 'qt5quicktest.dll'})
    unused_native_test = (normalized.startswith('numpy/_core/_multiarray_tests.')
                          or normalized in {'cython/utility/testcyutilityloader.pyx',
                                            'cython/utility/testutilityloader.c'})
    sample_data = normalized.startswith(('skimage/data/', 'sklearn/datasets/data/',
                                         'sklearn/datasets/descr/', 'sklearn/datasets/images/'))
    return (bool(set(parts[:-1]) & _DEV_DIRS) or sample_data or unused_test_binary
            or qt_development or unused_native_test
            or python_module in {n.lower() for n in _UNUSED_HELPERS}
            or filename.startswith('tcltest-')
            or filename.startswith('test_') or filename in {'test.py', 'conftest.py', 'setup.py',
                'setup.cfg', 'pyproject.toml', 'manifest.in', 'meson.build'}
            # skimage uses .pyi files as lazy-loader import maps at runtime.
            or (filename.endswith('.pyi') and not normalized.startswith('skimage/'))
            or filename.startswith('readme') or filename.endswith(('.pyc', '.pyo', '.dll.a', '.lib')))


def runtime_toc(entries, *, module=False):
    """Filter PyInstaller (destination, source, type) tuples in stable order."""
    return [entry for entry in entries if not development_payload(entry[0], module=module)]
