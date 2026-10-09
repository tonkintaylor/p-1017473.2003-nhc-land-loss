Added step 1 of the shaking hazard, at
`src/scripts/landloss/hazard/shaking/steps/s1_pga_realisation/`. It reads the
National Liquefaction Model's 2500-year site class 5 PGA grid through the new
`get_nlm_scenario_pga_2500yr_site_class_5`, clips it to the extent, and scales it
by one lognormal draw per realisation against a 10% coefficient of variation,
seeded from the project realisation stream.

The multiplier is drawn once for the whole field rather than per cell: drawing
per cell would destroy the spatial pattern and average away across a portfolio.

Worth knowing before anything reads the output: the NLM grid is national at
about 9,930 m across a cell, so one cell covers the whole pilot box and roughly
6 by 5 cells cover the four territorial authorities. Every property in the pilot
therefore reads the same PGA, and with the multiplier shared, every asset in a
realisation shakes identically.
