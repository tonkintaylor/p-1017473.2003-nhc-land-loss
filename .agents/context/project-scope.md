# Project scope

> Refinements below each item were added after the kick-off meeting on
> 16 September 2026. They annotate the agreed scope rather than replace it.

## Phase 1: Establish initial tool

The first phase would focus on establishing the process and understanding the key
variables controlling insurance claim costs. Key tasks in this phase would
include:

1. Decide on seismic demand — T+T propose to use the seismic demands from TS1170.5
   (2025), either the 2500y or 10,000y return period. Note: given the relatively
   small spatial extent of the study and the expected strong shaking (peak ground
   acceleration of ~1g) the spatial correlation effects typically captured in
   scenario analysis would have limited impact on the outputs, and return period
   based demands provide a better basis for social equality analysis.

   Refinements:

   - The TS1170.5 demands are confirmed as the basis; the remaining decision
     is the VS site class, expected to be one value for flat land and another
     for sloping land. Kevin Foster's site class work is an alternative.
   - The NHC loss modelling team accepted the single high-demand approach but
     noted that settlement behaviour, and therefore the equity conclusions,
     may differ at lower demands.
   - The project lead decided on 2026-10-02 to use the TS1170.5 2,500-year
     demands as the standard gives them, per site class (**T-26**). Over the
     pilot that is a PGA of 1.68 to 1.77 g on site classes II and III and
     1.00 to 1.27 g on classes IV and V, and a PGV of 1.1 to 2.0 m/s, which is
     larger than the roughly 1 g the scope was written around.
2. Decide on spatial extent that covers a portfolio that meets the requirements
   detailed in Bridget Attwood's email dated 10/09/26 (reproduced in
   `nhc-event-parameters-email.md`).

   Refinements:

   - Proposed extent is Wellington City, Lower Hutt, Upper Hutt and Porirua.
     Each of Bridget's principles was tested against it and passes; Porirua
     was added to be confident of capturing lower-value land.
   - The whole Wellington region was rejected as too large and too far from
     the population centres.
   - The difficult south coast of Wellington may be cut from the extent if it
     proves too complicated, and revisited later.
   - The unique identifier is expected to be the LINZ property ID, because
     insurance attaches at property rather than dwelling level.
3. Provide a prototype Excel based tool that implements 8–12 branches of a
   decision tree, where the selected variables and their values would be based on
   existing work to date by NHC and engineering judgement. Some key variables that
   would be considered include:
   1. Geospatial data (slope gradient etc.)
   2. Geological data
   3. Proportion of properties on flatland with exposure to liquefaction versus
      sloping land with exposure to landslide
   4. Proportion of properties with moderate and major-to-very severe liquefaction
      induced land damage and lateral spreading
   5. Proportion of properties expected to have a landslide within insured land
      defined by NHC's current policy
   6. Proportion of properties that have a retaining wall
   7. Service infrastructure
   8. Estimated repair costs for different damage states
   9. Land valuation
   10. Cost surge factors and property access
   11. Insurance penetration

   Refinements:

   - Geology, geomorphology and the flat versus sloping land split come from
     the National Liquefaction Model, as does the liquefaction damage given a
     level of shaking. The lateral spreading pilot has just finished its first
     stage and can be used too.
   - Slope gradient is calculated by T+T from the LINZ DEM, with more than one
     gradient measure likely: one feeding retaining walls and one feeding
     slope failure.
   - Retaining wall prevalence will be an SME estimate from Nick Peters,
     varied by suburb, with LIDAR used to inform roughly where within a suburb
     the walls are.
   - Insurance penetration is a fixed 90% per Bridget's brief, exposed as an
     editable model variable.
   - Land and capital values are expected from the councils rather than QV,
     which charges for the data.
   - Cost surge and property access were confirmed as already within the level
     of effort, including local surcharge effects.
   - Multi-unit buildings, cross-lease and shared land are excluded from this
     phase. This narrows the brief, which asked for them explicitly, and the
     exclusion is to be evidenced by quantifying what proportion of the
     population they represent.

## Phase 2: Refine estimates, additional variables

Based on the work from phase 1, the prioritisation of analyses to support
critical variables would be undertaken. This would lead to improvements to the
tool such that it can be used by NHC staff to explore the impact of different
settings and assumptions. Key tasks in this phase would include:

1. Refine critical variables. Examples could include:
   1. Use the National Liquefaction Model and associated land damage fragility
      curves to determine land damage for the selected seismic demand
   2. Quantify the proportion of properties on different thresholds of sloping
      ground
   3. Quantify through a pilot study area (~100 properties) what proportion have
      retaining walls
2. Include additional variables within the tool by evaluating claims settled from
   previous events to understand key attributes of a property that drive costs and
   understand the different reasons for a claim

   Refinements:

   - NHC can extract claims data but is unsure it can do so in time, and the
     data is not disaggregated by damage type. A sample of around 50 claims
     was offered; reviewing that by hand is considered worthwhile even if AI
     extraction is not viable.
   - The team should plan on the realistic assumption that no claims data
     arrives.
   - Existing Christchurch cost data held by T+T, and a possible unfiltered
     version held by Nathan at NHC that includes hill properties, are
     alternative sources.
   - The retaining wall pilot may be replaced or supplemented by a suburb-level
     SME estimate, with LIDAR analysis validated against SME judgement rather
     than the other way around.

## Phase 3: Probabilistic spatial analysis

This phase would be done in parallel with phase 2 and focuses on developing a
spatially explicit, asset-level Python model that complements the Excel tool.
Whereas the Excel tool assigns the total population of assets across branches of a
logic tree using cohort proportions and potentially a number of parametric
distributions, the Python model operates on individual properties, drawing on
geospatial and geological datasets to assign site-specific hazard and
vulnerability attributes to each asset. Uncertainty in key variables (e.g. repair
cost, damage state thresholds, infrastructure contribution) is propagated through
Monte Carlo simulation, allowing the full shape of the loss distribution to be
characterised rather than a single expected value.

This approach generates spatial outputs that enable the methods to be checked for
consistency and reliability, and more importantly evaluates the impact of the
simplifications inherent in the Excel tool. Two examples of where such
simplifications may have a material effect include:

- The use of a cap on losses can make losses sensitive to uncertainties in
  distributions which may not be captured with a simple logic.
- There is expected to be spatial correlation between variables, such as the
  height of retaining walls and the probability of a landslide. The correlation
  could mean higher costs than if the two variables were considered independent.
  This can only partially be accounted for in the Excel tool but is naturally
  captured by individual asset modelling.

Key tasks include:

1. Implement the probabilistic spatial model in Python, applying site-specific
   hazard and vulnerability attributes to individual properties and using Monte
   Carlo simulation to propagate uncertainty through to loss estimates at the
   asset, suburb, and portfolio level.
2. Produce comparisons between the Excel tool and the geostatistical approach.
3. Produce spatial maps of attributes, expected damage and losses for selected
   scenarios and policy settings.
4. Produce correlation plots, e.g. comparing damage or insured loss versus land
   value.
5. Produce per comparison and summary charts, e.g. number of claims per suburb.

Refinements:

- A decision is outstanding on whether to estimate the spatial extent of each
  landslide, or to classify each property as fully, partially or not affected.
  Extent modelling handles landslides crossing several properties; the simpler
  classification reaches an answer faster.
- Local guidance is that most earthquake-induced landslides will be confined to
  a single property and associated with a failed retaining wall, an oversteep
  cut or a fill embankment, with multi-property failures concentrated in
  gullies where colluvium and higher water tables allow global failures.
- The model is built end to end on assumptions first, then improved as datasets
  arrive; the modular structure is what makes this work.

## Phase 4: Reporting

This phase would collate the key findings to support:

- the current policy setting discussions,
- extending the study area, and
- the development of land damage vulnerability functions for probabilistic
  portfolio loss assessment.

Key tasks include:

1. A letter report would be produced to inform NHC of the evidence behind, and
   limitations of, the tool, covering the following:
   1. The evidence behind the adopted values for each variable.
   2. A description of the outputs when run through the Python based approach.
   3. A comparison between the tool and the more detailed Python scripts.
   4. Recommendations for future improvements that could refine estimates and be
      extended to wider perils and a broader spatial extent.
2. The code and datasets would be shared with the NHC loss modelling team.
3. Possible examples to inform the NHC exposure model: code to determine spatial
   extent of insured land per property, datasets on distributions of property
   assets (e.g. distribution of height of retaining walls).
4. Possible examples to inform the vulnerability model: evaluation of parameters
   influencing vulnerability at a selected (high shaking) demand, implementation
   of those parameters into a vulnerability analysis.
5. A workshop with the NHC loss modelling team to go through key results to inform
   how these can be used to update NHC's residential dwelling exposure model and
   how the damage predictions can be extended to lower shaking demand levels to be
   converted to land damage vulnerability functions.

Refinements:

- Reporting must carry the evidence behind assumptions, including the
  assumptions used to justify excluding parts of the population, so that the
  NHC board can see the exclusions were checked rather than asserted.
- The interpretation of the NHC Act and the exact land cover wording need to be
  agreed with NHC before the report can describe the policy settings, and the
  settings NHC wants tested have not yet been supplied.

## Out of scope

The following services are out-of-scope:

- Increased Liquefaction Vulnerability and Increased Flood Vulnerability
- Consideration of increased rain-induced slope failure following earthquake
  shaking
- Consideration of aftershocks
- Consideration of fault surface rupture hazard
- Consideration of tectonic subsidence / uplift

Refinements:

- Fault surface rupture was reconfirmed as excluded, despite a fault line
  running through the study area that would drive loss of property access.
- Multi-unit buildings, cross-lease and shared land are added to the exclusions
  in practice, parked for a possible later sub-study.
- Privately owned service connections cannot be mapped, as councils hold only
  public services and the connection points.
- Pipes are covered under the building rather than the land, so they fall outside
  the land loss model (Wgtn Land Model meeting, 21 September 2026).

## Deliverables

- Prototype xlsx based tool
- Refined draft tool
- Draft scenario outputs of probabilistic spatial analysis
- Final tool and draft letter report
- Final report, code and datasets handover
- Workshop with NHC loss modelling team
