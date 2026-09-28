Moving a policy control in the loss viewer was slow once the file got large.
The page was built against the 4,388-claim pilot, where rebuilding everything
on every keystroke is free; against the 98,263-claim region stress file it is
not, and typing a figure into the excess ceiling crawled.

Three things were doing the work over again for no gain.

**Markers were rebuilt on every render.** Every claim's `circleMarker` was
discarded and re-made to change the colour of the dots. They are now built once
per file and restyled in place, and the rows they carry are re-pointed rather
than re-bound.

**Every marker carried its own tooltip.** `bindTooltip` allocates an object per
claim, so the region file made a hundred thousand of them on every pass. One
shared `mouseover` handler now reads the row off the marker and reuses the
single tooltip the charts already use, so nothing is allocated on hover.

**Every keystroke settled the whole portfolio.** Typing `12500` is five
keystrokes and the page answered five times, throwing four away. The policy
inputs are now debounced at 180 ms.

Colouring the map and changing the basemap change neither the settlements nor
the charts, so those two controls now repaint without re-settling; they are
wired separately from the inputs that do change the answer. Window resizes are
debounced on the same path.

None of this changes a number the page reports -- `settle()` is untouched, and
`check_viewer_against_the_model` still proves the page and the module agree
before the CSV is written.
