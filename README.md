# Resource Manager for NVDA

An NVDA add-on that shows which applications are using the most CPU, in a fast,
fully keyboard-driven dialog you can actually navigate with a screen reader.

Windows Task Manager exposes its process list as a very large UI Automation data
grid whose values change constantly. That makes it slow and awkward to explore
with a screen reader. This add-on skips it entirely: it samples process activity
itself and presents the result as a small native list box, which NVDA reads
instantly.

## Features

- A popup dialog listing running applications sorted by CPU usage, with memory
  usage and process count for each.
- Processes are grouped per application, so a browser's forty helper processes
  appear as one row you can expand to see the individual children.
- CPU is reported as a percentage of the whole machine, the same way Task
  Manager reports it.
- Sort by CPU, memory, or name from a combo box in the dialog.
- End task on the selected application, with confirmation and a force-kill
  fallback for processes that will not close gracefully.
- Spoken shortcuts that announce the top few applications without opening any
  window at all.
- Settings in NVDA's own settings dialog for refresh behaviour and how much
  detail the spoken shortcuts include.

## Requirements

NVDA 2025.1 or later. No other dependencies. psutil, which this add-on uses to
read process activity, has shipped inside NVDA since version 2024.2.

## Keyboard commands

- `NVDA+alt+R` opens the Resource Manager dialog.
- Announcing the top applications by CPU, and by memory, are available as
  unassigned commands. Bind them to whatever you like under Resource Manager in
  NVDA's Input Gestures dialog.

Inside the dialog: arrow keys move through the list, right arrow or enter
expands an application to show its individual processes, left arrow collapses it
again, tab reaches the sort combo box and the buttons, and escape closes.

## Building from source

Run `python build.py`. This produces `resourceManager-<version>.nvda-addon` in
the repository root, which you can open to install. No build toolchain beyond a
Python 3 interpreter is required.

## Licence

GNU General Public License version 2, the same licence as NVDA itself. See
[LICENSE](LICENSE).

This add-on uses psutil, which is distributed under the 3-clause BSD licence.

## Credits

Written by CodedByGoose, with the help of Quill (Claude agent).
