from __future__ import annotations

import json

from nero_wrapper.cli import config_main, read_state_main


def test_config_command_prints_json_without_credentials(capsys: object) -> None:
    assert config_main([]) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    document = json.loads(output)
    assert document["firmware"] == "v112"
    assert "password" not in output.lower()


def test_read_state_is_dry_run_by_default(capsys: object) -> None:
    assert read_state_main(["--arm", "arm_b"]) == 0

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert '"channel": "can_arm_b"' in output
    assert "Dry run only" in output
