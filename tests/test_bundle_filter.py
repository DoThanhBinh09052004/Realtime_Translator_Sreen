import pytest
from tools.bundle_filter import development_payload, runtime_toc


@pytest.mark.parametrize('name', [
    'scipy/io/tests/data/example.mat', 'Cython/Debugger/Tests/test_gdb.py',
    'paddleocr/tools/test_hubserving.py', 'skimage/data/camera.png',
    'sklearn/datasets/data/iris.csv', 'cv2/samples/__init__.pyi',
    'package/__pycache__/runtime.pyc', 'paddleocr/README.md',
    'scipy/special/_test_internal.cp310-win_amd64.pyd',
    'shapely/testing.py', 'PyQt5/Qt5/qml/QtTest/TestCase.qml',
    'paddle/distributed/launch/plugins/test.py',
    'numpy/_core/_multiarray_tests.cp310-win_amd64.pyd',
    'Cython/Utility/TestUtilityLoader.c',
])
def test_excludes_development_files(name):
    assert development_payload(name)


@pytest.mark.parametrize('name', [
    'assets/ocr/dict/japan_dict.txt', 'assets/ocr/cls/inference.pdmodel',
    'paddleocr/ppocr/data/imaug/operators.py', 'certifi/cacert.pem',
    'PyQt5/Qt5/translations/qt_en.qm', 'PyQt5/Qt5/plugins/platforms/qwindows.dll',
    'paddleocr/LICENSE', 'assets/ocr/NOTICE.paddleocr.txt',
    'scipy/stats/_binomtest.py', 'scipy/_lib/_testutils.py',
    'skimage/__init__.pyi', 'skimage/transform/__init__.pyi',
])
def test_preserves_runtime_resources(name):
    assert not development_payload(name)


def test_filters_suites_but_preserves_import_time_helpers_and_statistics():
    keep = ['scipy._lib._testutils', 'numpy._pytesttester',
            'anyio._core._testing', 'skimage._shared.tester', 'scipy.stats._binomtest',
            'numpy.testing._private.utils', 'numpy._core.tests', 'numpy._core.tests._natype']
    drop = ['scipy.stats.tests.test_stats', 'Cython.Debugger.Tests',
            'numpy.testing.tests.test_utils', 'sklearn.utils._testing',
            'paddleocr.tools.test_hubserving', 'scipy.conftest']
    entries = [(name, 'source.py', 'PYMODULE') for name in keep + drop]
    assert [entry[0] for entry in runtime_toc(entries, module=True)] == keep
