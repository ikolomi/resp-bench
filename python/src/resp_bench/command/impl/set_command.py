"""SET command implementation."""

from ..command import Command, CommandResult


class SetCommand(Command):
    def __init__(self, config):
        super().__init__(config)
        pattern = b"0123456789ABCDEF"
        self._value = (pattern * ((self.data_size_bytes // len(pattern)) + 1))[
            : self.data_size_bytes
        ]

    def execute_sync(self, client, key_generator) -> CommandResult:
        key = key_generator.next_key()
        result = client.set(key, self._value)
        return CommandResult(
            command_name=self.name,
            latency_micros=result.latency_micros,
            success=result.success,
        )

    async def execute_async(self, client, key_generator) -> CommandResult:
        key = key_generator.next_key()
        result = await client.set(key, self._value)
        return CommandResult(
            command_name=self.name,
            latency_micros=result.latency_micros,
            success=result.success,
        )
