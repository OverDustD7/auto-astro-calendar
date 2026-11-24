# Release preparation

Record the exact commit, dirty files, skill version, intended channel and actual candidate hash. Preserve existing edits and wanted reports before changes. Do not infer a released version from skill metadata or a local archive filename.

Use the regression commands in the root README for affected calculation, narrative or layout changes. Record environment, results and limits. Tests that generate files must use owned temporary output. Rendering checks require visual inspection of actual pages; numerical tests do not establish page layout or scientific correctness for every date.

Prepare an explicit archive file list. Exclude `out/`, local caches, audit evidence, credentials, temporary files and the original screenshot-bearing layout sample. Keep the fallback format fixture and required source/data files. Inspect the resulting archive, including nested Word XML and metadata, example images and assets. Check location coordinates and attribution deliberately.

Include the MIT LICENSE for original code and original documentation. Check third-party rights separately. Preserve third-party notices and verify redistribution rights for examples, data and imagery. A checked source tree does not clear older archives or Git history.

Publication and history cleanup are separate authorized actions. Restore changed files from this round's before copies when prior edits exist; never reset the whole workspace or delete wanted reports as rollback.
