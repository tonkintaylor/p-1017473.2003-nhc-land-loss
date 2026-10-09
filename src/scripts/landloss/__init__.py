"""Scripts that build and check the landloss models.

Each module mirrors the library package of the same name, including its
submodules: ``exposure`` by asset type, ``hazard`` by hazard, and ``vul`` by
hazard then asset type. Within any of those, ``steps`` builds the model,
``validations`` checks its intermediate and final outputs, ``report`` produces
the figures and tables the report uses, and ``research`` holds exploratory work
that is not part of the reported pipeline.

Those four appear at whichever level the work belongs to. Work specific to one
asset or one hazard sits in that submodule; work shared across all of them --
the address spine, the valley cross-sections, the NHC claims datasets -- sits at
the module level. None of the four is created until there is something to put in
it.
"""
