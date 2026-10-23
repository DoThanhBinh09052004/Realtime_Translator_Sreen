from types import SimpleNamespace


def test_affinity_success_restore_and_failures(monkeypatch):
    from ui import capture_exclusion as policy
    calls = []
    class Fn:
        def __init__(self, fn): self.fn = fn
        def __call__(self, *args): return self.fn(*args)
    def get(hwnd, out):
        out._obj.value = calls[-1]
        return 1
    api = SimpleNamespace(SetWindowDisplayAffinity=Fn(lambda hwnd, value: calls.append(value) or 1),
                          GetWindowDisplayAffinity=Fn(get))
    monkeypatch.setattr(policy, '_windows_build', lambda: 19041)
    monkeypatch.setattr(policy, '_user32', lambda: api)
    assert policy.set_capture_excluded(123) is None
    assert policy.set_capture_excluded(123, False) is None
    assert calls == [0x11, 0]
    monkeypatch.setattr(policy, '_windows_build', lambda: 19040)
    assert policy.set_capture_excluded(123).code == 'capture_exclusion'
    monkeypatch.setattr(policy, '_windows_build', lambda: 19041)
    api.SetWindowDisplayAffinity = Fn(lambda *a: 0)
    assert policy.set_capture_excluded(123).code == 'capture_exclusion'
    api.SetWindowDisplayAffinity = Fn(lambda *a: 1)
    assert policy.set_capture_excluded(123).code == 'capture_exclusion'
