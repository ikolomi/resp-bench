"""Weighted command selector."""

import random


class CommandSelector:
    def __init__(self, commands):
        self._commands = commands
        total = sum(c.weight for c in commands) or 1.0
        cumulative = []
        s = 0.0
        for c in commands:
            s += c.weight / total
            cumulative.append(s)
        self._cumulative = cumulative
        self._rng = random.Random()

    def select(self):
        r = self._rng.random()
        for i, threshold in enumerate(self._cumulative):
            if r <= threshold:
                return self._commands[i]
        return self._commands[-1]
