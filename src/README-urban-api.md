# Buildings from Urban API

Source supplied by the researcher: https://urban-api.testing.idulab.ru/api/docs
OpenAPI is `/api/openapi` (without `.json`). Schema and type dictionary
were archived in `results/urban-api-*-20261109.json`.

Territory search returned federal city Saint Petersburg `3138` and nested
settlement `192713`. Use `3138` with `include_child_territories=true` to include
the federal city's subordinate territories. This does not prove completeness
of the underlying database.

The type dictionary identifies function `1` as building, type `4` as residential
house and type `5` as non-residential building. Unfiltered physical objects also
include parks and other non-buildings; do not count all objects as buildings.

```powershell
python src/collect_urban_objects.py --territory 3138 --function 1 --output data/urban-api-spb-buildings-20261109
```

The collector saves original UTF-8 JSON pages, request URLs, checksums and a
manifest, follows API next links and resumes cached pages only when URLs match.
`--max-pages 1` is a diagnostic limit. Rerun without this limit to continue.
`pagination_finished` means traversal ended; before analysis, separately check
unique physical object IDs, count stability, geometry validity and type coverage.
Download date is not the data observation date. Keep API `created_at` and
`updated_at` attributes. Do not use building counts as population estimates.

No account credentials are embedded in the collector. API response failures
remain visible in the manifest; the collector does not bypass authorization.
