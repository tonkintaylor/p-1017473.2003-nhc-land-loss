"""What a landslide polygon does to the ground it covers: the land classes.

Every landslide polygon the hazard module writes, from the large model and the
urban model alike, carries one of three classes in :data:`LAND_CLASS_COLUMN`:

- :data:`EVACUATED`: ground the failure removed. Loss of support, where the
  land under or beside a property went.
- :data:`INUNDATED`: ground the debris came to rest on, which may have started
  on somebody else's property entirely.
- :data:`IMMINENT`: ground left standing immediately behind an urban failure's
  headscarp, at risk of going next. Only the urban model writes it, and the
  land damage step ignores it until the register decides how it is settled
  (**T-45**).

Evacuated polygons never overlap one another; inundated and imminent polygons
may. The vocabulary lives here, in hazard, so that it is read downstream in the
module order (hazard, then exposure, then vul, then loss) and no hazard module
imports :mod:`landloss.vul`.
"""

LAND_CLASS_COLUMN = "land_class"

EVACUATED = "evacuated land"
INUNDATED = "inundated land"
IMMINENT = "imminent land"

LAND_CLASSES = (EVACUATED, INUNDATED, IMMINENT)
