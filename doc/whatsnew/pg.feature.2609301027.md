**The damaged face area reaches the report row.** `reports.csv` now carries
each wall's damaged face area from the Summary of Information table as a list
(`wall_damaged_faces_m2`, in the same order as `wall_lengths_m`), and the
damaged and imminently damaged face areas summed over the property's walls.

`walls.csv` gains `damaged_length_from_face_m`, the damaged face area over the
retained height: a second reading of the damaged length taken from the summary
table rather than the property damage bullets. It is the only reading where the
bullets give no length, and where both exist a disagreement marks a report
worth opening. On the report it was checked against, the two agree for every wall.
