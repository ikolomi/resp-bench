"""PING command implementation."""

from ..command import Command, CommandResult


class PingCommand(Command):
    def execute_sync(self, client, key_generator) -> CommandResult:
        result = client.ping()
        return CommandResult(
            command_name=self.name,
            latency_micros=result.latency_micros,
            success=result.success,
        )

    async def execute_async(self, client, key_generator) -> CommandResult:
        result = await client.ping()
        return CommandResult(
            command_name=self.name,
            latency_micros=result.latency_micros,
            success=result.success,
        )
