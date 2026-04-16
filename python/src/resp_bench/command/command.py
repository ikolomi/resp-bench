"""Command result and base class."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandResult:
    command_name: str
    latency_micros: int
    success: bool


class Command:
    """Abstract base for benchmark commands."""

    def __init__(self, config):
        self.weight = config.weight
        self.name = config.command.upper()
        self.data_size_bytes = config.data_size_bytes

    def execute_sync(self, client, key_generator) -> CommandResult:
        raise NotImplementedError

    async def execute_async(self, client, key_generator) -> CommandResult:
        raise NotImplementedError
