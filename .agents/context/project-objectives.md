# Project objectives

NHC seeks support from Tonkin + Taylor to provide an evidence-based tool to
evaluate difference in policy settings relating to land damage cover.

Evidence would be drawn from existing NHC work, engineering judgement, data
science and existing literature, and would be developed in a way to support
broader predictive modelling of land damage beyond the initial extent and perils
scoped for this work.

Tonkin + Taylor would work in an agile, collaborative manner where prioritisation
of improvements to the tool (e.g. adding additional logic, refining estimates
through further data analysis, and adding additional outputs) would be agreed
with the NHC project manager.

## Refinements

Added following the kick-off meeting on 16 September 2026. These clarify the
objectives above; where one appears to narrow the agreed scope it is noted as
such.

- The deliverable is a **relativity test between policy options**, not an absolute
  forecast of the cost of land damage. Total cost matters only insofar as it lets
  the options be compared, and no figure from the tool should be presented as a
  standalone estimate.
- NHC's primary interest is the **affordability** of the total cost of land
  damage. That places a large share of the weight on how many landslides are
  predicted, which is also one of the larger uncertainties in the work.
- The study area is proposed as **Wellington City, Lower Hutt, Upper Hutt and
  Porirua**, subject to confirmation by NHC. The whole Wellington region was
  judged too large and too far from the population centres.
- **Bridget Attwood is the single point of contact**, with a weekly check-in, and
  distributes internally within NHC. This supersedes the earlier suggestion of
  separate contacts for loss modelling and claims data, and keeps the interface
  simple.
- The working method is to build the model **end to end on assumptions first**,
  then spend the remaining time improving the inputs. Because the model is
  modular, datasets can be swapped in as they arrive and the outputs converge.
- Assumptions that shape the answer need **evidence behind them, not just
  judgement** — including the assumptions used to justify excluding something.
  A decision to park an issue should be accompanied by a check of how much of the
  population it affects.

Added following the land model catch-up on 30 September 2026:

- **Everything upstream of `loss` produces what an NHC claim report contains**
  -- evacuated, inundated and imminently damaged land, and the damaged
  structures -- and `loss` does the costing from that. For liquefaction this
  means the hazard and vulnerability modules now hand over evacuated and
  inundated areas per land damage state rather than a cost per state
  (**T-55** to **T-57**).
- The timeline: a **first model the team is happy with by about Tuesday
  6 October 2026**, then around two days reviewing every status document to
  decide what is done now and what moves to future improvements (**T-58**),
  and the **report by 14 October 2026** (**T-59**). The report is planned as a
  roughly three-page executive summary and a technical document of about
  100 pages written in the style of the NLM report, with its content held in
  YAML read into Typst and converted to docx so every statement is traceable.

Added following the Wgtn land model sense check on 5 October 2026:

- **What goes to Bridget Attwood on 14 October is a rough first pass**: a draft
  of the executive summary of about five pages, not a full draft report. John
  Leeves had always expected only a five-pager and said the budget does not
  cover a large report. It informs the paper Bridget writes: what the model
  does, its assumptions, what it does not do and could do in future, and a
  table of losses per land cap scenario. Numbers matter more than
  documentation, and further runs are expected once she has read it. The
  technical document above (**T-70**) is still built, for internal use and as
  the appendices (the lead, 2026-10-08).
- **Model work stops after Friday 9 October**, with the Wednesday 7 October
  session for John Leeves and Nick Peters to find holes in it; the rest is
  reporting. The paper goes to NHC's ELT about two weeks before the board,
  which John Leeves recalled as early November (about 6 November).
- **NHC wants the total loss under a land cap roughly unchanged from the
  current Act but more fairly distributed**, since wealthier suburbs are seen
  to receive much larger payments, so the report has to show the spread
  between suburbs as well as totals (**T-94**). The relative outcome for
  property owners matters more than the total.
