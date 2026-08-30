# Task Explorer

Task Explorer shows you which applications are using the most processor
time, in a small dialog built to be explored with a screen reader.

Windows Task Manager presents its process list as a very large data grid whose
values change constantly, which makes it slow and awkward to move through. This
add-on does not use Task Manager at all. It measures process activity itself and
puts the result in an ordinary list box, which NVDA reads immediately.

## Opening the list

Press `NVDA+alt+E`.

The dialog opens with the busiest application selected, so you are on the
application you most likely came to find as soon as it appears.

Overall processor and memory use are on `alt+T`, spoken only when you ask.
They are deliberately not announced as the dialog opens: NVDA announces the
dialog and the selected item at that moment, and anything the add-on said would
simply be cut off.

Each line tells you everything about one application in a single sentence, for
example:

Google Chrome, 12 percent CPU, 1.4 GB, 40 processes, collapsed

Processor use is given as a percentage of your whole machine, the same way Task
Manager gives it. An application using one core fully on an eight core computer
reads as 12 percent, not 100 percent.

## Moving around

- Up and down arrows move through the list.
- Typing jumps to an application by name. Keep typing to narrow it down: `s`
  then `l` finds Slack rather than the first application beginning with l. A
  pause of about a second and a half starts a new search. Typing part of a name
  works too, so `chrome` finds Google Chrome. Only the rows you can see are
  searched, so a search never jumps inside a collapsed application. Pressing the
  same letter over and over still steps through everything beginning with it.
- Right arrow, or enter, expands an application to show its individual
  processes. Applications made of a single process do not expand, and do not
  claim to be collapsed.
- Left arrow collapses it again. Pressing left arrow while on one of the
  individual processes takes you back up to the application it belongs to.
- Tab reaches the sort combo box and the buttons.
- `F5` updates the list immediately.
- `alt+T` announces overall processor and memory use.
- `alt+1`, `alt+2` and `alt+3` sort by processor use, memory use and name.
- Escape closes the dialog.

## Sorting

The sort combo box above the list offers processor use, memory use, and name.
Processor use is the default. You can also switch without leaving the list:
`alt+1` sorts by processor use, `alt+2` by memory use and `alt+3` by name, and
the new order is announced as it is applied. Applications that are using the same amount are
kept in a stable order, so rows do not swap places under you for no reason.

## Ending a task

Select an application and press the End task button.

You will be asked to confirm, and the confirmation tells you how many processes
will close.

Task Explorer first asks the application to close, in exactly the way
clicking its close button would. The application runs its own shutdown and may
prompt you to save your work. If it is still running a few seconds later, you
are asked whether to force it, which is immediate and does lose unsaved work.

An application with no window, such as a background service, cannot be asked
politely at all. Task Explorer tells you so and offers to force it, rather
than pretending it tried something gentler.

Some things cannot be ended:

- NVDA itself is refused outright. Ending it would leave you with no speech and
  no way to get it back. Use NVDA's own menu if you want to exit.
- Critical Windows processes warn you first, in plain terms, before the usual
  confirmation.
- Applications running with higher privileges than NVDA cannot be closed by this
  add-on at all. Windows does not permit it, and you will be told so rather than
  left wondering why nothing happened.

## Announcing the busiest applications without opening anything

Three commands report usage without any window appearing.
Neither has a shortcut assigned out of the box, so they do not collide with
anything you already use. Assign them under Task Explorer in NVDA's Input
Gestures dialog:

- Announce the applications using the most processor time.
- Announce the applications using the most memory.
- Announce total processor and memory use for the whole machine.

How many applications they mention, and whether they mention memory as well as
processor use, are both settings.

## Settings

Task Explorer appears in NVDA's own Settings dialog, in the category list
alongside your other add-ons. You can set:

- Whether the list updates continuously, or pauses while you are moving through
  it. Pausing is worth choosing if you find the list distracting to read while
  values are changing.
- How often it updates, in seconds.
- How many applications the spoken shortcuts announce.
- Whether spoken summaries mention memory as well as processor use.

Whichever update mode you choose, the row you are currently sitting on is never
rewritten underneath you while the list has focus, and the list always keeps
your place by remembering which application you were on rather than which
position in the list you were at.

## Requirements

NVDA 2025.1 or later, tested through NVDA 2026.2. Nothing else needs
installing.

## Credits

Written by CodedByGoose, with the help of Quill (Claude agent).

Released under the GNU General Public License version 2, the same licence as
NVDA. Uses psutil, which ships with NVDA and is distributed under the 3-clause
BSD licence.
