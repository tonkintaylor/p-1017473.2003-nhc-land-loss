Added `release_updates/`, holding `weekly_update_template.typ` — an A4, narrow
margin Typst template for the weekly progress update to NHC, with a date and five
sections: general updates, then a table each for hazard, exposure, vulnerability
and loss. The hazard and vulnerability tables carry a column per hazard, exposure
a column per insured asset, and each has a `Current status` and a `What's next`
row of numbered lists; the vulnerability cells group their items by asset.

The new `writing-weekly-updates` skill generates one: it reads every `status.md`
under `src/scripts/landloss/`, summarises each to one-line items, composes the
general updates section, fills the template and writes
`update_week_of_<monday>.typ` beside it for the project lead to edit and
finalise. The generated update is compiled and the PDF left beside the `.typ` to be read;
`release_updates/*.pdf` is gitignored, because the `.typ` is the tracked source.

`release_updates/fill_update.py` does the substitution from a content JSON,
taking each handlebar's indentation from the template line it sits on and
failing hard on an unknown key, an unused key or a handlebar left in the output.
