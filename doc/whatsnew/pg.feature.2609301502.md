**The 2013 EQC template and the Nelson office's layout are read too.** Checked
against 85651.0043 (2013, Wellington) and 871351.8037 (2016, Nelson):

- "T&T Ref :" job numbers and the "Summary Information" heading (2013).
- The 2013 single imminent "Inundation" row, read as new inundation.
- Wall blocks with no number, like "Timber Pole retaining wall – 200 mm dia
  poles at 2m centres:", numbered in order.
- Damage given as a "section" of a wall rather than a "length" of it.
- Remedial works written as "replacing the damaged section of RTW1", with the
  construction taken from the next line.

`reports.csv` gains `claim_accepted`, from the summary's "Is this Natural
Disaster damage?". A declined claim reads False, and its "Nil" areas mean
nothing was accepted, not that no land moved. Where there is no event
sentence, `event_cause` now falls back to the claim heading, e.g.
"(Earthquake) Damage".
