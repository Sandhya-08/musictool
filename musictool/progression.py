from __future__ import annotations

import functools
import itertools

from musictool.chord import SpecificChord
from musictool.note import SpecificNote
from musictool.util.cache import Cached


class Progression(Cached):
    def __init__(self, chords: tuple[SpecificChord, ...], /):
        self.chords = chords
        if not all(isinstance(x, SpecificChord) for x in chords):
            raise TypeError('only SpecificChord items allowed')

    def __getitem__(self, item):
        return self.chords[item]

    def __len__(self):
        return len(self.chords)

    def __repr__(self):
        return f'Progression{self.chords})'

    def all(self, checks__):
        return all(check(a, b) for a, b in itertools.pairwise(self) for check in checks__)

    def all_not(self, checks__):
        return all(not check(a, b) for a, b in itertools.pairwise(self) for check in checks__)

    @property
    def distance(self):
        n = len(self)
        return sum(abs(self[i] - self[(i + 1) % n]) for i in range(n))

    def transpose_unique_key(self, origin_name: bool = True):
        origin = self[0][0]
        key = tuple(frozenset(note - origin for note in chord.notes) for chord in self)
        if origin_name:
            return origin.abstract.i, key
        return key

    def __add__(self, other: int) -> Progression:
        if not isinstance(other, int):
            raise TypeError('only adding integers is allowed (transposition)')
        return Progression(tuple(chord + other for chord in self))

    @functools.cached_property
    def transposed_to_C0(self) -> Progression:
        return self + (SpecificNote('C', 0) - self[0][0])
