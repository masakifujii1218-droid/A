import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sub


def test_route_selection_is_removed_from_slash_commands():
    for command_name in ["create_auto", "create", "create_emp", "create_man"]:
        command = getattr(sub, command_name)
        callback = getattr(command, "callback", command)
        parameters = inspect.signature(callback).parameters
        assert "路線名" not in parameters, f"{command_name} should not accept a route selection parameter"
