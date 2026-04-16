"""GET command implementation."""

from ..command import Command, CommandResult


class GetCommand(Command):
    def execute_sync(self, client, key_generator) -> CommandResult:
        key = key_generator.next_key()
        result = client.get(key)
        return CommandResult(
            command_name=self.name,
            latency_micros=result.latency_micros,
            success=result.success,
        )

    async def execute_async(self, client, key_generator) -> CommandResult:
        key = key_generator.next_key()
        result = await client.get(key)
        return CommandResult(
            command_name=self.name,
            latency_micros=result.latency_micros,
            success=result.success,
        )
