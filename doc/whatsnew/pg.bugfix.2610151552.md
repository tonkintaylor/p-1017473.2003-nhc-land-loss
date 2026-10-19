Resolve relative GeoPackage paths before archive integrity checks and close
SQLite connections explicitly, avoiding false damage reports and leaked handles.