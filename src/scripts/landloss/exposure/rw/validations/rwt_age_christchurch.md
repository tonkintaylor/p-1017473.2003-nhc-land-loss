# Retaining wall age against Christchurch's building ages: findings

Run 2026-10-02 by `table_rwt_age_christchurch.py`, over LINZ NZ Property
Boundaries version 448299, NZ Addresses 447993, NZ Property Titles List 447940
and the open District Valuation Roll 114085 version 448300.

## Question

Exposure step 8 dates every claim property's retaining walls from the issue date
of its titles and the date of the survey plan its lot is on
(`landloss.exposure.rw.age`). The study area holds no building ages to check
that against. How well do the rules recover building age where it is known,
and which rules earn their place?

## Method

- Christchurch is the one city with an open valuation roll and housing of every
  era. Its claim properties are built exactly as Wellington's
  (`build_claim_properties`), and dated by the same function
  (`infer_claim_ages`).
- The truth for a claim is the oldest building the roll dates on its footprint
  (`residential_decades`, `footprint_rows`): residential rating units only,
  vacant land and mixed-age codes left out. Building age is taken as wall age.
- The roll dates to a decade, so a claim's truth is spread over the bins in
  proportion to its decade's years (`age.bin_shares_of_span`). A claim scores
  the share of its truth in the bin it was put in. The ceiling is about 0.92,
  because a 1990s or 2000s house can only score part of a point in any one bin.
- Each rule is switched off in turn (`VARIANTS`). Every variant is scored over
  all 130,243 claims with a dated dwelling, and again without the 7,482 (5.7%)
  rebuild suspects: a 2010s or later dwelling on a title and plan both older
  than 2010, overwhelmingly the post-earthquake rebuild, which no rule reading
  titles can see and Wellington has no equivalent of. Leaving them out selects
  on the truth, so it is read for the comparison between variants, not for the
  level.
- Suburbs with at least 100 scored claims (82 of them) are compared on the
  error in each bin's share (`suburb_comparison`).

## Results

`report/exposure/rw/rwt-age/tab/rwt-age-christchurch-summary.csv`:

| Variant | Claims | Bin score | Right decade | Share error, summed | Suburb error, median | Suburb error, 90th pct |
| --- | --- | --- | --- | --- | --- | --- |
| Title date only | all | 0.671 | 0.600 | 0.281 | 0.066 | 0.194 |
| Title date only | no rebuilds | 0.698 | 0.637 | 0.273 | 0.053 | 0.210 |
| With the reissue rule | all | 0.743 | 0.637 | 0.080 | 0.031 | 0.115 |
| With the reissue rule | no rebuilds | 0.774 | 0.676 | 0.075 | 0.029 | 0.082 |
| **Rules as coded** | all | **0.747** | 0.634 | 0.104 | 0.030 | 0.127 |
| **Rules as coded** | no rebuilds | **0.779** | 0.672 | **0.039** | **0.025** | 0.084 |
| Cross-leases on their own title | all | 0.732 | 0.636 | 0.129 | 0.043 | 0.126 |
| Cross-leases on their own title | no rebuilds | 0.763 | 0.674 | 0.103 | 0.031 | 0.109 |

The bin shares over all claims, against the roll's:

| | `pre_1970` | `1970_1991` | `1992_2004` | `2005_on` |
| --- | --- | --- | --- | --- |
| Title date only | 0.260 | 0.267 | 0.174 | 0.299 |
| Rules as coded | 0.396 | 0.179 | 0.137 | 0.287 |
| The roll | 0.369 | 0.188 | 0.112 | 0.331 |
| Rules as coded, no rebuilds | 0.393 | 0.180 | 0.136 | 0.291 |
| The roll, no rebuilds | 0.392 | 0.200 | 0.119 | 0.290 |

By the rule that set the year
(`rwt-age-christchurch-by-basis.csv`): the title's own date 101,948 claims,
scoring 0.746; the plan's date 25,276, scoring 0.780; infill Lot 1 3,012,
scoring 0.500; the neighbours' date 7.

Per suburb (`rwt-age-christchurch-by-suburb.csv`, all claims), the median error
in a bin's share is 2 to 6 points, and 65% of suburbs are within 10 points in
every bin. The worst are the Port Hills and coastal suburbs rebuilt after the
earthquakes (Southshore, Redcliffs, Huntsbury, Mount Pleasant), read too old;
Fendalton, also rebuilt heavily; Kainga and Spencerville, former bach
settlements whose titles are young; and Northwood, a 1990s and 2000s
subdivision whose houses followed their titles across the 2005 break.

## Findings

- **The raw title date is a poor guide to old houses.** More than half of
  Christchurch's pre-1950 houses sit on titles issued in 1970 or later. Most are
  paper certificates of title reissued on a later dealing; under the electronic
  register (about 2002) a dealing no longer creates a title, so the reissue is a
  paper-era effect. The raw title puts `pre_1970` 11 points low.
- **Dating the lot's plan fixes most of it.** The deposited plan is not
  reissued, and its number dates it: within the Canterbury district, DP 1,000
  falls about 1911, DP 10,000 about 1932, DP 30,000 about 1973 and DP 60,000
  about 1992, and national numbers from DP 300,000 run from 2001. Using the
  plan's date for a paper title more than five years younger than its plan
  lifts the bin score from 0.671 to 0.743 and cuts the share error by more
  than two thirds. Applied to every title regardless of format, it scored
  about the same in exploration (0.729 against 0.728, per rating unit); the
  paper-only form is kept because it follows the mechanism. An electronic
  title is never a reissue, and one on an old plan usually carries a new
  house.
- **Cross-leases belong with the reissue rule, unit titles do not.** On a whole
  claim property, a cross-leased lot's oldest building is the house that
  stood there before the flats were added, so its plan dates it better than its
  lease (0.747 against 0.732). A unit title is created when its block is built,
  and its own date is best.
- **Most infill lots carry a new house; Lot 1 of a two-lot plan often does
  not.** Moving every young lot among older neighbours to their date made the
  estimate worse in every setting tried. But Lot 1 of a two-lot plan dated more
  than 25 years younger than its neighbours kept an older house over half the
  time, against a quarter for Lot 2, which fits a plan drawn with the existing
  house on Lot 1. Dating those Lot 1s by their neighbours adds 0.004 to the bin
  score and, without the rebuilds, halves the share error (0.075 to 0.039).
  A 35-year gap gave closer shares than 25 for the same score.
- **A build lag was tried and not kept.** Adding one to four years to a
  title's date, for the time a house takes to follow its title, improves the
  all-claims shares only by moving houses into `2005_on` in place of the
  rebuilds; without the rebuilds, even one year worsens the share error (0.039
  to 0.044) for a 0.003 gain in score.
- **What is left is mostly the rebuild.** Without the rebuild suspects every
  bin share is within two points of the roll's. With them, `2005_on` is four
  points low and `pre_1970` three high.

## Implications for Wellington

- Wellington has had no rebuild on Christchurch's scale, so the
  no-rebuilds row is the closer guide to how the rules do there: a property in
  the right bin about 78% of the time against a ceiling of about 92%, the
  study-area shares within a few points, and a typical suburb within 2 to 3
  points in each bin.
- Ordinary redevelopment, a house replaced on its old section, still reads
  old, and nothing in the titles shows it. Inner suburbs with much of it, and
  any with a run of demolitions, will read older than they are.
- The Wellington plan dates are fitted the same way from Wellington's own
  titles and cannot be checked against a roll; the fitted dates the step prints
  (DP 10,000 about 1931, DP 30,000 about 1969, DP 60,000 about 1987, DP 90,000
  about 2001) are in line with Canterbury's.

## Caveats

- Building age is taken as wall age, and the oldest building as the claim's. A
  wall rebuilt after the house is younger than its bin.
- The roll's own building ages are a valuer's record, coded to a decade, and
  not checked here.
- The rules were tuned and scored on the same Christchurch claims. The numbers
  are few and each is a choice between a handful of settings, so the risk of
  overfitting is small, but the scores are in-sample.
