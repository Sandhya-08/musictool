import functools
import itertools

import pipe21 as P

from . import config
from .chord import Chord
from .chord import SpecificChord
from .chord import name_to_intervals
from .note import SpecificNote


def all_triads(octaves=(4, 5, 6)):
    all_notes = tuple(
        SpecificNote(note, octave)
        for octave, note in itertools.product(octaves, config.chromatic_notes)
    )
    n3 = tuple(itertools.combinations(all_notes, 3))  # all 3-notes subsets
    all_chords = frozenset(
        Chord.from_name(root, name)
        for root, name in itertools.product(config.chromatic_notes, name_to_intervals)
    )

    rootless_2_rootfull = {chord.rootless: chord for chord in all_chords}

    return (
        n3
        | P.Map(frozenset)
        | P.Map(SpecificChord)
        | P.ValueBy(lambda chord: rootless_2_rootfull.get(chord.abstract))
        | P.FilterValues()
        | P.Append(lambda x: f'{x[1].root.name} {x[1].name}')
        | P.Pipe(tuple)
    )


@functools.cache
def have_parallel_interval(a: SpecificChord, b: SpecificChord, interval: int) -> bool:
    '''
    parallel in same voices!
    if there'are eg fifth in 1st and fifth in 2nd chord but not from same voices
    - then it allowed (aint considered parallel) (test it)

    a1 - b1
    a0 - b0
    todo: what about fifths + octave (eg C5 G6 -> F5 C6)
    '''
    voice_transitions = tuple(zip(a.notes_ascending, b.notes_ascending))
    for (a0, b0), (a1, b1) in itertools.combinations(voice_transitions, 2):
        if abs(a0 - a1) == interval == abs(b0 - b1):
            return True
