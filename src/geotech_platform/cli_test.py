from __future__ import annotations

from geotech_platform import cli


def test_app_returns_interrupt_status_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_spec", lambda name: object())

    def raise_interrupt(command):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.subprocess, "run", raise_interrupt)

    assert cli.app() == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
