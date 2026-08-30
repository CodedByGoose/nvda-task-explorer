# Changelog

## Unreleased

Typing in the list now searches by whole name instead of by first letter. `s`
then `l` finds Slack, where before the l jumped to the first application
beginning with l. Part of a name works as well, so `chrome` finds Google Chrome.
Only the rows on screen are searched, so a search never jumps inside an
application you have left collapsed, and pressing the same letter repeatedly
still steps through everything beginning with it.

## Version 1.0.1

Tested with NVDA 2026.2, and `lastTestedNVDAVersion` raised to match.

NVDA 2026.1 reset the add-on compatibility baseline, so an add-on last tested
against 2025.3 is refused by every 2026 release. Because NVDA checks the minimum
version against the running release and the last tested version against that
release's compatibility floor, one build satisfies both: NVDA 2025.1 through
2026.2 are all covered by this single package.

No functional changes.

## Version 1.0

First release.

Task Explorer shows which applications are using the most processor time, in
a dialog built to be explored by ear.

- A dialog on `NVDA+alt+R` listing running applications ordered by processor
  use, with memory use and process count on the same line, so one arrow key
  press tells you everything about an application.
- Applications are grouped by executable, so a browser's forty helper processes
  are one row. Right arrow or enter expands it into the individual processes,
  left arrow collapses it again, and left arrow from a process takes you back to
  the application it belongs to.
- Processor use is reported as a percentage of the whole machine, the same way
  Task Manager reports it.
- Sorting by processor use, memory use or name, from a combo box or from
  `alt+1`, `alt+2` and `alt+3` without leaving the list.
- `alt+T` announces total processor and memory use. `F5` updates the list.
- End task asks the application to close first, exactly as clicking its close
  button would, so it can prompt you to save. Only if it is still running a few
  seconds later are you offered the choice to force it.
- NVDA itself is refused outright. Critical Windows processes warn first.
  Applications running with higher privileges than NVDA report that they cannot
  be closed, rather than failing silently.
- Three commands report usage without opening any window: the busiest
  applications by processor use, by memory use, and total machine utilisation.
  All three ship unassigned, to be bound from Input Gestures.
- Settings in NVDA's own settings dialog for update behaviour, update interval,
  how many applications the spoken commands announce, and whether they mention
  memory.

Notes on how it works:

- Process activity is measured directly rather than read from Task Manager,
  whose process list is a very large data grid that is slow to navigate with a
  screen reader.
- Every process is read in a single system call per sampling pass. Reading the
  same figures through psutil alone costs roughly 750 milliseconds per pass on a
  machine running 345 processes, because psutil falls back to a full system
  enumeration for each process it cannot open. A pass now costs about 6
  milliseconds, and processes a normal user cannot open stay visible instead of
  reading as zero.
- The fast path checks itself against psutil at startup and falls back to the
  slower psutil route if the two ever disagree.
