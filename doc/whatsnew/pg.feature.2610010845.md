**A folder that cannot be read no longer stops a fetch.** One access-restricted
subproject folder (1502000.1937) stopped the whole IAG run; it is now skipped
with a message and recorded as unreadable.

`extract_claim_reports.py --show SUBPROJECT …` prints the header lines, the
property damage and imminent risk paragraphs, and every summary table row the
parse sees for a cached report, for diagnosing a template it misses. A declined
claim is no longer reported as missing fields: it has no areas to find.
