# Resource Manager

Resource Manager shows you which applications are using the most processor
time, in a small dialog built to be explored with a screen reader.

Windows Task Manager presents its process list as a very large data grid whose
values change constantly, which makes it slow and awkward to move through. This
add-on does not use Task Manager at all. It measures process activity itself and
puts the result in an ordinary list box, which NVDA reads immediately.

## Opening the list

Press `NVDA+alt+R`.

The dialog opens with the busiest application selected, and announces overall
processor and memory use as it appears. You can turn that announcement off in
settings.

Each line tells you everything about one application in a single sentence, for
example:

Google Chrome, 12 percent CPU, 1.4 GB, 40 processes, collapsed

Processor use is given as a percentage of your whole machine, the same way Task
Manager gives it. An application using one core fully on an eight core computer
reads as 12 percent, not 100 percent.

## Moving around

- Up and down arrows move through the list.
- Right arrow, or enter, expands an application to show its individual
  processes. Applications made of a single process do not expand, and do not
  claim to be collapsed.
- Left arrow collapses it again. Pressing left arrow while on one of the
  individual processes takes you back up to the application it belongs to.
- Tab reaches the sort combo box and the buttons.
- `F5` updates the list immediately.
- Escape closes the dialog.

## Sorting

The sort combo box above the list offers processor use, memory use, and name.
Processor use is the default. Applications that are using the same amount are
kept in a stable order, so rows do not swap places under you for no reason.

## Ending a task

Select an application and press the End task button.

You will be asked to confirm, and the confirmation tells you how many processes
will close. Resource Manager first asks the application to close politely. If it
is still running a few seconds later, you are asked whether to force it, which
is immediate and loses unsaved work.

Some things cannot be ended:

- NVDA itself is refused outright. Ending it would leave you with no speech and
  no way to get it back. Use NVDA's own menu if you want to exit.
- Critical Windows processes warn you first, in plain terms, before the usual
  confirmation.
- Applications running with higher privileges than NVDA cannot be closed by this
  add-on at all. Windows does not permit it, and you will be told so rather than
  left wondering why nothing happened.

## Announcing the busiest applications without opening anything

Two commands announce the top few applications without any window appearing.
Neither has a shortcut assigned out of the box, so they do not collide with
anything you already use. Assign them under Resource Manager in NVDA's Input
Gestures dialog:

- Announce the applications using the most processor time.
- Announce the applications using the most memory.

How many applications they mention, and whether they mention memory as well as
processor use, are both settings.

## Settings

Resource Manager appears in NVDA's own Settings dialog, in the category list
alongside your other add-ons. You can set:

- Whether the list updates continuously, or pauses while you are moving through
  it. Pausing is worth choosing if you find the list distracting to read while
  values are changing.
- How often it updates, in seconds.
- How many applications the spoken shortcuts announce.
- Whether spoken summaries mention memory as well as processor use.
- Whether overall totals are announced when the dialog opens.

Whichever update mode you choose, the row you are currently sitting on is never
rewritten underneath you while the list has focus, and the list always keeps
your place by remembering which application you were on rather than which
position in the list you were at.

## Requirements

NVDA 2025.1 or later. Nothing else needs installing.

## Credits

Written by CodedByGoose, with the help of Quill (Claude agent).

Released under the GNU General Public License version 2, the same licence as
NVDA. Uses psutil, which ships with NVDA and is distributed under the 3-clause
BSD licence.
