"""Java-compatible LCG random number generator."""


class JavaRandom:
    """Port of java.util.Random for cross-language deterministic sequences."""

    _MULTIPLIER = 0x5DEECE66D
    _ADDEND = 0xB
    _MASK = (1 << 48) - 1

    def __init__(self, seed: int):
        self._seed = (seed ^ self._MULTIPLIER) & self._MASK

    def next_int(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("bound must be positive")
        # Power of 2
        if (bound & -bound) == bound:
            return (bound * self._next_bits(31)) >> 31
        # General case - rejection sampling
        while True:
            bits = self._next_bits(31)
            val = bits % bound
            if bits - val + (bound - 1) >= 0:
                return val

    def _next_bits(self, bits: int) -> int:
        self._seed = ((self._seed * self._MULTIPLIER) + self._ADDEND) & self._MASK
        return self._seed >> (48 - bits)
