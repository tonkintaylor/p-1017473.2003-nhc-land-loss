// Appendix: the ground model. Written for readers of the technical report, who
// have not seen the code: say what the method does, not where it lives.
// Numbers from:
//
//     uv run --frozen python src/scripts/landloss/ground/report/gen_report_numbers.py
//
// Method from ground steps 1 (s1_terrain) and 2 (s2_ground_map); the class
// mappings are in landloss.hazard.landslide.ground_map. The limitations carry
// their register IDs in comments.

#import "../lib.typ": inputs-table, limitations-table, num, pct, review

#let g = yaml("/report/ground/tab/report-numbers.yaml")
#let s = g.settings
#let x = g.study_area
#let share(table, key) = table.at(key, default: 0)

= Ground model <ground-model>

== Context

The retaining wall and landslide models need to know, for any point in the
study area, what the ground is made of, whether it has been cut or filled, how
wet it is, and how steep it is. No single map gives all four, so the model
builds a ground map by combining several, and a set of terrain grids from the
LiDAR elevation model. @retaining-walls uses this information to identify
places where retaining walls may be present. @landslide-damage uses it to
estimate how likely slopes are to fail.

== Inputs

@ground-inputs-table lists the sources the ground model combines.

#figure(
  inputs-table(
    [Ground elevation, 1 m grid], [LINZ, from LiDAR where flown and the 8 m
      contour model elsewhere], [CC BY 4.0],
    [Engineering geology and earthworks of urban Wellington City],
    [GNS Science SLIDE (Wellington) materials and genesis maps
      @townsend_2020], [To confirm],
    [Geology, 1:50,000], [Geology of the Wellington area
      @begg_mazengarb_1996], [To confirm],
    [Geomorphology, flatland extent and groundwater depth],
    [National Liquefaction Model @tonkin_taylor_2026], [--],
    [Mapped cut and fill areas], [Wellington City Council], [To confirm],
  ),
  caption: [Inputs to the ground model.],
) <ground-inputs-table>

#review[Confirm the licences of the SLIDE maps, the 1:50,000 geology and the
Wellington City Council cut and fill layer, and the exact name of the council
layer.]

== Method

=== Terrain grids

The 1 m elevation grid is averaged into coarser grids of
#s.dem_resolutions_m.map(r => num(r)).join(", ", last: " and ") m. Larger
cells are excluded if more than half of the cell is sea or otherwise lacks
reliable ground-elevation data. This prevents the sea from lowering the
calculated elevation near the coast. Slope and aspect are calculated on the
#s.slope_resolutions_m.map(r => num(r)).join(", ", last: " and ") m grids, not
the 1 m grid. This is because the 1 m grid captures small features such as
kerbs, driveways and garden steps. These can make a hillside appear steeper or
more irregular than it is at the scale relevant to the study.

Two additional measures describe whether a location is above or below the
surrounding land:

- Possible cut and fill: the model compares the detailed 1 m elevation map
  with a smoother map of the surrounding land, using a
  #num(s.residual_bases_m.first()) m or #num(s.residual_bases_m.last()) m
  smoothing distance. The difference between the two maps is called the
  cut-and-fill residual. Positive values indicate ground that is higher than
  the surrounding surface and may have been built up with fill; negative values
  indicate ground that is lower and may have been cut down. However, the method
  cannot reliably distinguish human earthworks from natural landforms: natural
  benches may appear as fill, while natural gullies may appear as cut (see
  @ground-combining).
- Topographic position: the elevation of each location compared with the
  surrounding ground within #num(s.tpi_windows_m.first()) m. Positive values
  identify ridges and crests, while negative values identify gullies and
  hollows. The landslide model uses this information when estimating where a
  landslide is most likely to begin.

=== Ground attributes

Each point in the ground map carries four attributes:

- Material: rock, colluvium, loess, alluvium, uncontrolled fill, engineered
  fill, or unknown. All rock is treated as the same type of rock -- highly to
  completely weathered greywacke -- because the available maps do not show how
  strongly the rock has weathered in different places. Some SLIDE map classes
  contain both natural ground and fill, for example, "mixed fill and rock". For
  these areas, the model uses the named natural material but separately records
  that the ground has been filled. Reading them all as fill made most of urban
  Wellington's mapped ground fill.
- Modification: cut, fill or natural. Where it is fill, the fill thickness is
  the mean height of the #num(s.residual_bases_m.last()) m residual over the
  filled area.
- Groundwater: saturated where the NLM median depth to groundwater is under
  #num(s.saturated_depth_m) m, poorly drained where it is under
  #num(s.poorly_drained_depth_m) m, and well drained otherwise. The NLM
  covers only flatland, so the hills take a default depth of
  #num(s.default_groundwater_depth_m) m, which is well drained.
- Prior failure: a relict or recent landslide where SLIDE maps one, and none
  elsewhere.

The material sets the geology factor of the Kingsbury slope rating
@kingsbury_1995, used in @landslide-damage. Rock takes a factor of
#num(s.geology_values.rock) and every soil and fill
#num(s.geology_values.colluvium), on a scale of 0 to 10.

The model converts the cut-and-fill residual into mapped areas by averaging it
within #num(s.residual_class_cell_m) m cells. A cell is classified as cut if it
is more than #num(s.residual_threshold_m) m below the smoothed surface and as
fill if it is more than #num(s.residual_threshold_m) m above it. Patches smaller
than #num(s.residual_min_patch_m2) m#super[2], which is one 30 m cell and the
smallest the residual can resolve, are merged into their largest neighbour. The
boundaries are then smoothed over #num(s.residual_simplify_m) m to reduce the
blocky appearance caused by the grid.

=== Combining the sources <ground-combining>

The sources overlap and disagree, so each attribute is taken from the most
reliable source that covers the point, in the order of @ground-precedence-table.
Where no source covers it, the attribute takes its default. The map is built
by cutting the study area into pieces along every source boundary, so that
each piece lies wholly inside or outside each source polygon.

#figure(
  table(
    columns: (1fr, 3fr, 1.2fr),
    align: left,
    table.header([*Attribute*], [*Sources, most preferred first*], [*Default*]),
    [Material],
    [SLIDE materials (high, then medium, then low confidence); 1:50,000
      geology; NLM geomorphology],
    [Unknown],

    [Modification],
    [SLIDE genesis (cut slopes, fill bodies, landfills, then dams); council
      cut areas; council fill areas; SLIDE fill materials; the cut and fill
      residual],
    [Natural],

    [Groundwater], [NLM depth to groundwater],
    [#num(s.default_groundwater_depth_m) m, well drained],

    [Prior failure], [SLIDE genesis], [None],
  ),
  caption: [The order in which sources set each attribute.],
) <ground-precedence-table>

SLIDE is preferred wherever it exists, because it was mapped for urban
Wellington slope hazard from site investigation records and aerial imagery
@townsend_2020. It covers only urban Wellington City, so the rest of the study
area relies on the regional geology and the NLM.

== Results

@ground-results-table summarises the ground map in each territorial authority.
Rock underlies about #pct(x.material.rock) of the land. The cut-and-fill
residual determines the modification category for
#pct(x.residual_share_of_modification) of the study area. It labels a large
amount of land as cut or fill. This is partly because, in hilly areas, the
method can mistake natural spurs and benches for fill and natural gullies for
cut. The median fill thickness is #num(x.fill_thickness_m.median, digits: 1)
m.

#figure(
  table(
    columns: (1.6fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1.2fr),
    align: (left, right, right, right, right, right, right),
    table.header(
      [*Territorial authority*], [*Rock*], [*Alluvium*], [*Cut*], [*Fill*],
      [*Natural*], [*Set by residual*],
    ),
    ..g.by_authority.pairs().map(((name, v)) => (
      name,
      pct(share(v.material, "rock")),
      pct(share(v.material, "alluvium")),
      pct(share(v.modification, "cut")),
      pct(share(v.modification, "fill")),
      pct(share(v.modification, "natural")),
      pct(v.residual_share_of_modification),
    )).flatten(),
  ),
  caption: [Share of each territorial authority's land by material and
    modification, and the share whose modification is set by the cut and fill
    residual.],
) <ground-results-table>

#review[The residual labels well over half of the land cut or fill, most of it
natural hillside. Wall candidates and Kingsbury ratings both read it, so check
whether this should be disclosed more strongly, or the residual confined to
urban land before the appendix goes out.]

== Limitations and future improvements

// L-12 mixed LiDAR vintages; L-49 single greywacke, weathering not mapped;
// L-57 Pleistocene alluvium in Porirua not on the geological maps; L-16 NLM
// simplifies sloping land; residual reads natural terrain (s2 method); T-89
// Wellington Fault sheared zone; QMAP not read; no reclamation source.
Beyond the limitations stated in the main report, several others may affect the
overall conclusions of the study. @ground-limitations-table lists each, its
likely effect on the modelled losses, and the improvement that would address
it.

#figure(
  limitations-table(
    (
      [The cut and fill residual reads natural spurs and benches as fill and
        gullies as cut, and it sets the modification over most of the land.],
      [*Over-prediction.* Cut and fill raise the Kingsbury rating and the
        chance of a wall.],
      [Confine the residual to urban land, or replace it with mapped
        earthworks compared between pre- and post-development elevation
        models.],
    ),
    (
      [Rock is modelled as a single, highly to completely weathered greywacke.
        Stronger rock and the crushed rock along active faults, including the
        Wellington Fault, are not distinguished.],
      [*Mixed.* Stronger rock is rated too susceptible, and crushed rock not
        susceptible enough.],
      [Map weathering grade from SLIDE and site records, and treat the sheared
        zones of active faults as weaker rock.],
    ),
    (
      [Outside urban Wellington City, materials come from regional geology and
        the NLM, which simplify sloping land and miss Pleistocene alluvium in
        Porirua.],
      [*Unknown.*],
      [Add revised local geology, such as the latest Porirua mapping, as a
        source above the regional maps.],
    ),
    (
      [Engineered fill and reclaimed land are not distinguished from
        uncontrolled fill, except where the NLM maps compacted fill.],
      [*Over-prediction*, where engineered fill is treated as uncontrolled.],
      [Add council and consent records of engineered fill and reclamation.],
    ),
    (
      [Groundwater depth is known only on flatland; the hills take a default
        that is well drained.],
      [*Under-prediction* on wet hillsides.],
      [Use a regional groundwater or wetness index for sloping land.],
    ),
    (
      [The elevation model merges LiDAR flown in different years, so recent
        earthworks show in some areas and not others.],
      [*Unknown.*],
      [Record the survey date of each area and refresh the elevation model as
        new LiDAR is flown.],
    ),
  ),
  caption: [Limitations, their impact on losses and future improvements.],
) <ground-limitations-table>

#review[The impacts on losses in @ground-limitations-table are a first draft.
Check the direction given for each.]
