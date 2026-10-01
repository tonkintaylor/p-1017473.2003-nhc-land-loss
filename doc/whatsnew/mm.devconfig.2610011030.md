Added the `pushing-to-koordinates` skill, which creates a layer in the National Liquefaction
Model Koordinates groups on the first push and adds a new version on later ones, with a
server-side style from the house colours. It is a dry run unless told to apply, records layer
IDs in `registry.json`, and refuses groups outside the NLM ones. Create was tested against
group 5452; update is ported from the NLM repo and untested here.
