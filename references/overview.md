<!-- PRIMER: overview
  STATUS: regenerated 2026-04-26 from docs.surveycto.com -->

# SurveyCTO Overview

SurveyCTO is a secure, scalable data-collection platform for researchers and professionals, especially in mobile, field, and offline settings. It supports collecting high-quality data on mobile devices with SurveyCTO Collect, in web forms, and in CATI workflows; its server distributes blank forms, receives submissions, manages users and workflows, monitors incoming data, and exports or publishes data onward. See the [SurveyCTO high-level overview](https://docs.surveycto.com/01-getting-started/01-overview/01.high-level-overview.html), the [SurveyCTO documentation home](https://docs.surveycto.com/), and the product site's [positioning](https://www.surveycto.com/).

For an agent, the key orientation is this: SurveyCTO work usually means editing or reasoning about definition files that configure survey instruments, server datasets, or monitoring workbooks. Those files sit inside a broader platform that handles form design, collection, quality monitoring, review/correction, exporting, publishing, offline workflows, and integrations.

## Relationship to XLSForm and ODK

SurveyCTO was originally based on [Open Data Kit (ODK)](https://opendatakit.org/) and uses spreadsheet form definitions that are closely related to XLSForm. SurveyCTO documentation describes form definitions as Excel or Google Sheets workbooks, and the canonical SurveyCTO spreadsheet form definition has three worksheets: `survey`, `choices`, and `settings` ([forms intro](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html)).

Do not treat SurveyCTO as generic ODK. SurveyCTO has many ODK/XLSForm parallels, but also platform-specific fields, functions, appearance options, publishing features, workflow features, and expression behavior. High-impact gotchas to keep in working memory:

- Equality in SurveyCTO expressions is `=`, as shown in the SurveyCTO [expression reference](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html); do not assume `==`.
- Skip logic is normally expressed in the `relevance` property/column, matching SurveyCTO's docs on [implementing skip patterns with relevance](https://docs.surveycto.com/02-designing-forms/01-core-concepts/08.relevance.html).
- Numeric division uses `div`, not `/`, in SurveyCTO's documented numeric operators ([expression reference](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-numbers)).
- For `select_multiple`, use `selected()` to test selected choices; SurveyCTO's `select_multiple` docs say constraints and relevance need `selected()` for choice checks ([select_multiple field type](https://docs.surveycto.com/02-designing-forms/01-core-concepts/03i.field-types-select-multiple.html)).
- Use `choice-label()` for labels in static choice lists; SurveyCTO describes it as a similar, improved version of old `jr:choice-name()` ([expression reference](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-select_one-and-select_multiple-fields)).
- Use `index()` inside repeat groups; SurveyCTO explicitly advises it instead of ODK `position(..)` because `position(..)` can fail in some nested-group cases ([expression reference](https://docs.surveycto.com/02-designing-forms/01-core-concepts/09.expressions.html#working-with-repeated-data)).

This overview only flags the traps. For actual form authoring or expression debugging, go to [`xlsform.md`](xlsform.md) and [`expressions.md`](expressions.md).

## Definition File Types

| Definition file | How to recognize it | What it defines | What it is for |
| --- | --- | --- | --- |
| XLSForm form definition | `.xlsx` workbook with `survey`, `choices`, and `settings` worksheets | A SurveyCTO form: questions/fields, labels, choice lists, groups, repeats, calculations, constraints, relevance, form-level settings | Designing instruments that users fill out in SurveyCTO Collect or web forms; SurveyCTO also lets users edit forms in the online designer and export/import the spreadsheet definition ([forms intro](https://docs.surveycto.com/02-designing-forms/01-core-concepts/01.intro.html)) |
| Server dataset definition | `.xml` file whose main/root element is `<dataset>` | A server dataset's ID, title, fields/columns, unique record field, form links, data links, and dataset-specific options | Defining or recreating server datasets used for pre-loading, publishing, enumerators, cases, and other data workflows; the Support Center's XML article is the canonical practical reference for hand-editing these files ([server dataset XML files](https://support.surveycto.com/hc/en-us/articles/1500000322461-Working-with-server-dataset-XML-files)) |
| Data Explorer workbook definition | `.xlsx` workbook with `summaries`, `settings`, `global_filters`, and `global_exclusions` worksheets, often plus matching `*-help` worksheets | A Data Explorer workbook: field and relationship summaries, summary grouping, global filters, exclusions, title, and workbook ID | Configuring monitoring and exploration views for form submissions or dataset data; advanced mode can export/import these workbook definitions and attach datasets for merged-in context ([advanced Data Explorer workbooks](https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/04.advanced-data-explorer.html)) |

## Forms, Datasets, and Data Flow

SurveyCTO datasets are server-managed tables of rows and columns. The dataset intro says they can provide pre-loaded data to forms, receive published data from forms, and manage enumerator lists or case lists ([datasets intro](https://docs.surveycto.com/05-exporting-and-publishing-data/04-advanced-publishing-with-datasets/01.datasets-intro.html)).

The central pattern is bidirectional:

- Forms publish into datasets. In the server dataset XML, publishing is represented by `<dataLinks>` containing `<dataLink>` elements; incoming links from forms have a `FORM` data link class and `INCOMING` type in the Support Center XML reference ([server dataset XML files](https://support.surveycto.com/hc/en-us/articles/1500000322461-Working-with-server-dataset-XML-files)). In the UI/docs, this is "publishing form data into server datasets" ([publishing forms to datasets](https://docs.surveycto.com/05-exporting-and-publishing-data/04-advanced-publishing-with-datasets/02.forms-to-datasets.html)).
- Datasets pre-load into forms. In dataset XML, attached forms are represented by `<formLinks>` containing `<formLink>` elements; conceptually, each form link attaches the dataset to a form for pre-loading ([server dataset XML files](https://support.surveycto.com/hc/en-us/articles/1500000322461-Working-with-server-dataset-XML-files)). The SurveyCTO pre-loading docs describe the same workflow as creating a server dataset and attaching it to a form ([pre-loading data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/03.preloading.html)).
- `pulldata()` consumes pre-loaded data by pulling a value from an attached dataset or CSV into a calculate field or calculated default ([pre-loading data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/03.preloading.html)).
- `search()` consumes pre-loaded data for dynamic `select_one` and `select_multiple` choice lists; its source can be an attached CSV filename or an attached dataset ID ([loading choices from pre-loaded data](https://docs.surveycto.com/02-designing-forms/03-advanced-topics/04.search-and-select.html)).
- Case management is a special server-dataset workflow. SurveyCTO stores the case list in a server dataset, centers collection around cases rather than forms, can expose one or more forms for each case, and can use the `caseid` field to store the selected case ID in submissions ([case management](https://docs.surveycto.com/03-collecting-data/03-data-collection-workflow/02.case-management.html)).

Data Explorer sits downstream of form submissions. Advanced workbooks can attach server datasets and merge their columns into summaries and individual-submission views, which is useful when form data needs context from other forms or outside systems ([advanced Data Explorer workbooks](https://docs.surveycto.com/04-monitoring-and-management/02-managing-for-quality/04.advanced-data-explorer.html)).

## Authoritative Source Hierarchy

Use sources in this order:

1. [docs.surveycto.com](https://docs.surveycto.com/) for current product documentation and feature behavior.
2. [support.surveycto.com](https://support.surveycto.com/) for Support Center how-tos, operational guidance, and details not fully covered in product docs.
3. [www.surveycto.com](https://www.surveycto.com/) for high-level product positioning, feature pages, case studies, and marketing context.

When a primer and live documentation disagree, prefer live documentation. When a source is ambiguous, say so and avoid inventing behavior.

## Where To Go Next

- Read [`xlsform.md`](xlsform.md) when you need to edit, review, or generate SurveyCTO form definitions in `.xlsx` format.
- Read [`translation.md`](translation.md) when you need to add, update, or verify translations of form labels in an XLSForm.
- Read [`expressions.md`](expressions.md) when you need to write or debug relevance, constraints, calculations, choice filters, `pulldata()`, `search()`, or SurveyCTO-vs-ODK expression differences.
- Read [`datasets-xml.md`](datasets-xml.md) when you need to inspect or modify server dataset definition XML, including `formLinks`, `dataLinks`, unique IDs, case datasets, or enumerator datasets.
- Read [`data-explorer.md`](data-explorer.md) when you need to configure or troubleshoot Data Explorer workbook definitions, summaries, global filters, global exclusions, or attached dataset merges.
