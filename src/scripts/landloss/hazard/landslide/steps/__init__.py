"""The steps that build the landslide hazard model.

Steps 1 to 6 are run by ``gen_hazard.py`` in the order they run, after the ground
and exposure modules. Steps 7 and 8 are not run there: they are alternative
coverage models for the large landslides (the GWRC susceptibility rebuild and the
Kritikos et al. 2015 model), run by hand.
"""
