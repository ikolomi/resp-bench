"""Command factory."""

from .impl.get_command import GetCommand
from .impl.ping_command import PingCommand
from .impl.set_command import SetCommand

_COMMANDS = {
    "ping": PingCommand,
    "get": GetCommand,
    "set": SetCommand,
}


def create_command(config):
    cls = _COMMANDS.get(config.command)
    if cls is None:
        raise ValueError(
            f"Unknown command: {config.command}. "
            f"Supported: {', '.join(_COMMANDS.keys())}"
        )
    return cls(config)


def create_all_commands(configs):
    return [create_command(c) for c in configs]
