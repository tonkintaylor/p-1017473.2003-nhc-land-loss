**Koordinates and LINZ layers download with `KOOPCACHE_DIR` left unset.**
`.env.example` says to leave it unset, and the repository's own caches default
to `.koopcache` at the repo root, but ttpy reads the variable for itself and
refused to download any layer without it. The readers now hand ttpy the
resolved cache root before every download, so a fresh setup works, and a
relative value from an older `.env` no longer sends ttpy's downloads to the
directory a script was launched from.
