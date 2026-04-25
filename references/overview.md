<!--
  PRIMER: overview
  STATUS: STUB — to be regenerated from docs.surveycto.com via the prompt in
  README.md ("Regenerating primers"). Keep this file short and high-level;
  detailed mechanics belong in xlsform.md, expressions.md, datasets-xml.md,
  and data-explorer.md.
-->

# SurveyCTO Overview

SurveyCTO is a mobile data collection platform built on the [XLSForm](https://xlsform.org/) and [ODK](https://getodk.org/) standards, with platform-specific extensions and divergences. Survey designers author three kinds of definition files; together they describe forms, the datasets those forms feed, and the dashboards that monitor them.

## The three definition file types

| File type | Format | Purpose | Primer |
| --- | --- | --- | --- |
| **XLSForm form definition** | `.xlsx` (worksheets `survey`, `choices`, `settings`) | The survey instrument: questions, logic, calculations, choice lists, repeats, groups | [`xlsform.md`](xlsform.md) |
| **Server dataset definition** | `.xml` (root `<dataset>`) | Server-side dataset structure, form attachments, publishing rules, case management | [`datasets-xml.md`](datasets-xml.md) |
| **Data Explorer workbook** | `.xlsx` (worksheets `summaries`, `settings`, `global_filters`, `global_exclusions`) | Monitoring dashboard configuration | [`data-explorer.md`](data-explorer.md) |

Forms collect data → forms publish to datasets via dataset XML rules → Data Explorer workbooks visualize the published data. Forms can also *consume* datasets at fill-time via `pulldata()` and `search()`.

## How forms relate to datasets

- **Form → dataset (publishing)**: a `<dataLink>` in the dataset XML pulls submissions from a form into a dataset (server-side; `INCOMING` direction).
- **Dataset → form (pre-loading)**: a `<formLink>` attaches the dataset to a form so its rows are available offline; the form references rows via `pulldata()`, `search()`, or `select_one`/`select_multiple` against pre-loaded choice lists.
- **Case management**: a special dataset configuration where each row is a "case"; forms read case state, the platform tracks workflow status, and updates publish back into the dataset.

## SurveyCTO vs. generic XLSForm/ODK

SurveyCTO inherits XLSForm syntax and ODK semantics but has diverged in several places. **Do not assume generic ODK examples work in SurveyCTO without checking.** Notable conventions:

- Equality is `=`, not `==`.
- Skip logic column is `relevance`, not `relevant`.
- Current repeat instance is `index()`, not `position()`.
- Choice label lookup is `choice-label()`, not `jr:choice-name()`.
- Division operator is `div`, not `/`.
- For `select_multiple`, always use `selected()`; `=` does not work.

See [`expressions.md`](expressions.md) for the full expression-language primer and SurveyCTO-vs-ODK gotchas.

## Authoritative sources

When in doubt, consult these in order:

1. [docs.surveycto.com](https://docs.surveycto.com) — product documentation (current behavior, feature reference).
2. [support.surveycto.com](https://support.surveycto.com) — Support Center articles (deeper how-tos, edge cases).
3. [www.surveycto.com](https://www.surveycto.com) — marketing/site content (high-level positioning).

The primers in this directory are bundled stable summaries. They are not a substitute for the live docs when behavior may have changed.

## Where to go next

- Editing or debugging an XLSForm? Read [`xlsform.md`](xlsform.md), then [`expressions.md`](expressions.md) for any expression work.
- Working with a server dataset definition? Read [`datasets-xml.md`](datasets-xml.md).
- Configuring a Data Explorer dashboard? Read [`data-explorer.md`](data-explorer.md).
