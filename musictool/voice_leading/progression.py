from __future__ import annotations
import collections
import functools
import itertools
import random
from collections.abc import Iterable

import pipe21 as P

from musictool import config
from musictool.chord import Chord
from musictool.chord import SpecificChord
from musictool.note import SpecificNote
from musictool.noteset import NoteRange
from musictool.scale import Scale
from musictool.scale import parallel
from musictool.scale import relative
from musictool.voice_leading import checks


class Progression(list):
    def __init__(self, iterable=(), /):
        iterable = list(iterable)
        if not all(isinstance(x, SpecificChord) for x in iterable):
            raise TypeError('only SpecificChord items allowed')
        super().__init__(iterable)

    def all(self, checks__):
        return all(check(a, b) for a, b in itertools.pairwise(self) for check in checks__)

    def all_not(self, checks__):
        return all(not check(a, b) for a, b in itertools.pairwise(self) for check in checks__)

    @property
    def distance(self):
        n = len(self)
        return sum(abs(self[i] - self[(i + 1) % n]) for i in range(n))

    @property
    def transpose_unique_key(self):
        origin = self[0].notes_ascending[0]
        return origin.abstract.i, tuple(frozenset(note - origin for note in chord.notes) for chord in self)

    def transpose(self, origin: SpecificNote = SpecificNote('C', 0)) -> Progression:
        return Progression(chord.transpose(origin) for chord in self)


def all_triads(octaves=(4, 5, 6)):
    all_notes = tuple(
        SpecificNote(note, octave)
        for octave, note in itertools.product(octaves, config.chromatic_notes)
    )
    n3 = tuple(itertools.combinations(all_notes, 3))  # all 3-notes subsets
    all_chords = frozenset(
        Chord.from_name(root, name)
        for root, name in itertools.product(config.chromatic_notes, Chord.name_to_intervals)
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
def iter_inversions(chord: Chord, octaves):
    notes_iterators = []
    for note in chord.notes:
        notes_iterators.append([SpecificNote(note, octave) for octave in octaves])
    return itertools.product(*notes_iterators) | P.Map(lambda notes: SpecificChord(frozenset(notes), root=chord.root)) | P.Pipe(tuple)


def iter_inversions_chord_progression(progression, octaves):
    inversions = []
    for chord in progression:
        inversions.append(iter_inversions(chord, octaves))
    yield from itertools.product(*inversions)


@functools.cache
def check_all_transitions_not(p, f, *args):
    n = len(p)
    return all(not f(p[i], p[(i + 1) % n], *args) for i in range(n))


def no_double_leading_tone(p, s: Scale):
    '''leading tone here is 7th and 2nd not of a scale, maybe'''
    return all


def unique_roots(progression):
    return len(progression) == len(frozenset(chord.root for chord in progression))


def c_not_c(chords: Iterable[SpecificChord]) -> tuple[list[SpecificChord], list[SpecificChord]]:
    c_chords, not_c_chords = [], []
    for c in chords:
        if c.root.name == 'C':
            c_chords.append(c)
        else:
            not_c_chords.append(c)
    return c_chords, not_c_chords


def notes_are_chord(notes: tuple, scale_chords: frozenset[Chord]):
    abstract = tuple(n.abstract for n in notes)
    abstract_fz = frozenset(abstract)

    for chord in scale_chords:
        if abstract_fz == chord.notes:
            root = chord.root
            break
    else:
        return
    chord = SpecificChord(frozenset(notes), root)
    if chord[0].abstract != root:
        return
    yield chord


def possible_chords(scale: Scale, note_range: tuple[SpecificNote]) -> tuple[SpecificChord]:
    return (
        note_range
        | P.Filter(lambda note: note.abstract in scale.notes)
        | P.Pipe(lambda it: itertools.combinations(it, 4))  # 4 voice chords
        | P.FlatMap(lambda notes: notes_are_chord(notes, frozenset(chord for chord in scale.triads if chord.name != 'diminished')))
        | P.FilterFalse(checks.large_spacing)
        | P.Pipe(tuple)
    )


checks_ = (
    lambda a, b: checks.have_parallel_interval(a, b, 0),
    lambda a, b: checks.have_parallel_interval(a, b, 7),
    lambda a, b: checks.have_hidden_parallel(a, b, 0),
    lambda a, b: checks.have_hidden_parallel(a, b, 7),
    lambda a, b: checks.have_voice_crossing(a, b),
    lambda a, b: checks.have_large_leaps(a, b, 5),
)


@functools.cache
def no_bad_checks(a: SpecificChord, b: SpecificChord):
    return all(not check(a, b) for check in checks_)


# def make_progressions(
#     scale: Scale,
#     note_range: tuple[SpecificNote],
#     n=4,
# ):
#     return (
#         sequence_builder(
#             n,
#             options=possible_chords(scale, note_range),
#             curr_prev_constraint=no_bad_checks,
#             i_constraints={0: lambda chord: chord.root == scale.root},
#             unique_key=lambda chord: chord.root,
#         )
#         | P.Map(Progression)
#         | P.Pipe(lambda it: unique(it, key=operator.attrgetter('transpose_unique_key')))
#         | P.KeyBy(operator.attrgetter('distance'))
#         | P.Pipe(lambda x: sorted(x, key=operator.itemgetter(0)))
#         | P.Pipe(tuple)
#     )


@functools.cache
def all_chords(chord: Chord, note_range, n_notes: int = 3):
    chord_notes = tuple(n for n in note_range if n.abstract in chord.notes)
    return (
        itertools.combinations(chord_notes, n_notes)
        | P.Filter(lambda notes: frozenset(n.abstract for n in notes) == chord.notes)
        | P.Map(lambda notes: SpecificChord(notes, root=chord.root))
        | P.FilterFalse(checks.large_spacing)
        | P.Pipe(tuple)
    )


# def make_progressions_v2(
#     abstract_progression: tuple[Chord],
#     n_notes: int = 3,
# ):
#     chord_2_all_chords = tuple(all_chords(chord, config.note_range, n_notes) for chord in abstract_progression)
#     return (
#         sequence_builder(
#             n=len(abstract_progression),
#             options=chord_2_all_chords,
#             options_separated=True,
#             curr_prev_constraint=no_bad_checks,
#         )
#         | P.Map(Progression)
#         | P.Pipe(lambda it: unique(it, key=operator.attrgetter('transpose_unique_key')))
#         | P.KeyBy(operator.attrgetter('distance'))
#         | P.Pipe(lambda x: sorted(x, key=operator.itemgetter(0)))
#         | P.Pipe(tuple)
#     )


def random_progression(s: Scale, n: int = 8, parallel_prob=0.2):
    assert s.kind == 'diatonic'
    parallel_ = parallel(s)
    relative_ = relative(s)
    print('scale', 'parallel', 'relative')
    print(s, parallel_, relative_)
    print('=' * 100)
    chords = []
    chords.append(s.triads[0])

    steps = {'major': (0, 1, 2, 3, 4, 5), 'minor': (0, 2, 3, 4, 5, 6)}[s.name]  # disable diminished

    for _ in range(n - 1):
        step = random.choice(steps)
        s_ = s if random.random() > parallel_prob else parallel_
        c = s_.triads[step]
        print(s_, c)
        chords.append(c)
    return chords


def chord_transitons(
    chord: SpecificChord,
    noterange: NoteRange,
    unique_abstract: bool = False,
) -> frozenset[SpecificChord]:
    out = set()
    for note in chord:
        for add in (-1, 1):
            if (new_note := noterange.noteset.add_note(note, add)) not in noterange:
                continue
            notes = chord.notes - {note} | {new_note}
            if len(notes) != len(chord.notes):
                continue
            if unique_abstract and len(notes) > len({n.abstract for n in notes}):
                continue
            out.add(SpecificChord(notes))
    return frozenset(out)


def transition_graph(start_chord: SpecificChord, noterange: NoteRange) -> dict[SpecificChord, frozenset[SpecificChord]]:
    graph = collections.defaultdict(set)

    def _graph(chord: SpecificChord):
        if chord in graph:
            return
        childs = chord_transitons(chord, noterange)
        for child in childs:
            graph[chord].add(child)
        for child in childs:
            _graph(child)

    _graph(start_chord)
    graph = dict(graph)
    return graph
