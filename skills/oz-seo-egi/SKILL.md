---
name: oz-seo-egi
description: Analyze an Ozon product page together with Ozon Seller search-query XLSX/CSV exports, rank commercially relevant keywords, write three natural Russian SEO descriptions, and deliver a color-audited Excel workbook. Use for an Ozon SEO annotation based on query popularity and a product URL. Do not use for editing a live Ozon cabinet or inventing product claims.
---

# OZ SEO EGI

Turn an Ozon product page, search-query exports, and verified product facts into three distinct, auditable descriptions. Optimize first for the exact product, then for query popularity. Preserve source data, explain exclusions, and never invent properties.

## Mandatory product-link gate

An Ozon product URL is required before processing keywords or drafting text.

- If the link is missing, ask: `Пришлите, пожалуйста, ссылку на товар Ozon, чтобы я проверил его название и характеристики перед подготовкой SEO-текстов.` Then stop.
- Use the best read-only page-access capability available in the current host. Never assume that a tool named `@browser` exists.
- If an interactive browser or computer-use tool is available, open the exact URL and inspect the rendered product page. If only web search/page opening is available, open the exact URL with that capability. Use search only to locate the exact card; a search snippet is not evidence for product characteristics.
- If Ozon blocks the page or no web capability is available, ask for screenshots or copied blocks from `Название`, `О товаре`, `Описание`, `Состав`, and `Характеристики`. Treat clear user-supplied page materials as sourced evidence and continue. Do not stop merely because `@browser` is unavailable.
- Do not finalize from keywords alone. Stop only when neither the exact page nor sufficient user-supplied product evidence is available.
- Do not log in, edit the card, add to cart, or perform any other write action while analyzing the page.

## Required inputs

- Accessible Ozon product URL and current category-specific description limit.
- Ozon `.xlsx`, `.xls`, `.csv`, or `.tsv` query exports and a threshold for each source.
- Verified product facts with their source locations.
- A category profile and verified `product_type_terms`. Use `child_diapers` for детские подгузники, `laundry` for laundry products, and `generic` otherwise; for a generic profile, state the category phrase explicitly when it cannot be inferred from the title.
- Target brand, its aliases, known competitor brands, and other brands owned by the same seller when available.
- Reviewed `required_product_anchors`: the characteristics that every finished variant must contain in a key or ordinary text. The list may be empty only after an explicit commercial review.
- Reviewed `protected_broad_terms`: broad paid-search words that may appear only inside assigned keys. The list may be empty only after a lexical-risk review.

Do not hardcode a permanent Ozon limit. Verify it or ask before finalizing the workbook.

## Workflow

1. Enforce the product-link gate.
2. Read [references/product-page-analysis.md](references/product-page-analysis.md), use its capability-routing order to inspect the exact card or sufficient user-supplied page materials, and build a sourced fact snapshot, required anchors, brand aliases, and contradiction list.
3. Read [references/input-output-contract.md](references/input-output-contract.md) before processing files or building the workbook.
4. Read [references/seo-rules.md](references/seo-rules.md) before selecting keywords or drafting descriptions.
5. Preserve every source and all source metrics. Locate the header in the first 20 rows; support one- and two-row Ozon headers. If normal XLSX reading fails, use the script's value-only OOXML fallback.
6. Run `scripts/seo_pipeline.py prepare` with the sourced config. Use relevance as the admission gate. Among accepted queries, build each assigned sequence as a popularity ladder from the highest popularity to the lowest.
7. Resolve every `needs_review` brand and every conflicting fact before drafting. Do not silently choose a convenient claim.
8. Review all accepted queries, then assign as many distinct, fact-compatible, non-nested keys as the description limit and natural copy allow. Split them into `core`, `extension`, and `experimental`. Within each finished variant, sort all assigned keys by non-increasing popularity, regardless of tier.
9. Draft exactly three naturally written variants from `accepted_rows`: `Основной` uses only `core`; `Расширенный` uses `core + extension`; `Тестовый` uses `core + experimental`. Only the initial SEO block must begin sentences with assigned exact keys. After that, write ordinary buyer-facing sentences with verified characteristics, advantages, and use cases.
10. Run a human-language pass. When available, use `humanizer-ru` while preserving facts, exact assigned keys, protected-term budgets, and anchor coverage.
11. Save the text and assignments in the descriptions JSON format and run `scripts/seo_pipeline.py audit`.
12. Fix both technical and commercial errors. A global pass is allowed only when both statuses pass.
13. For `.xlsx`, load and follow the available `Spreadsheets` skill. Build, recalculate, render, and visually inspect the workbook defined in the contract.

## Non-negotiable rules

- Relevance is a gate: an irrelevant or factually incompatible query is excluded regardless of popularity. After that gate, popularity determines the order of assigned keys.
- Build the ladder by popularity, not by nesting: the first key is the most popular selected relevant query, followed by selected relevant queries in non-increasing popularity. Every key must occur in the accepted export.
- Do not assign a short phrase together with a longer phrase containing it in the same variant. For example, `гель для душа` must not be assigned alongside `гель для душа женский` or `гель для душа парфюмированный`. The two longer phrases may both be assigned if each is relevant and neither contains the other. Use `strict` overlap handling.
- Naturalness is mandatory for every variant; it is not a separate low-SEO strategy. If adding a key makes the copy visibly mechanical, remove or demote that key instead of sacrificing readability.
- Reuse the same `core` in all three variants. The sets must still differ through controlled additions: `extension` for safe relevant coverage and `experimental` for testable secondary semantics.
- `core`, `extension`, and `experimental` contain only accepted, fact-compatible queries. Experimental means lower-priority or broader, not unsupported, misleading, or irrelevant.
- Do not stop at a fixed small number of keys. Try the next eligible non-nested query in popularity order until adding it would exceed the limit, repeat the same meaning without benefit, or make the copy mechanical. Record why each accepted but unused query was left out. Keep at least one key in each tier when the three variants can be validated.
- `seo_sentence_count` equals the number of assigned keys. Those first sentences start with the exact keys in descending popularity order and contain meaningful continuation. Later sentences need not start with keys.
- A keyword is unique within a variant. Do not add unassigned broad commercial terms in continuations.
- Keep `protected_broad_terms` within the literal budget created by assigned keys. This includes deceptively general words such as `гель`, even when they also name the product type.
- Keep internal SEO explanations out of customer copy. Ban `поисковый запрос`, `поисковый синоним`, `этот ключ`, `в карточке`, `по характеристикам товара`, `форма выпуска`, and similar commentary.
- Continue an awkward synonym key with a verified buyer benefit or usage fact. Never correct or explain the key inside the description.
- Exclude competitor brands, other seller-owned brands not targeted by the card, below-threshold rows, duplicates, irrelevant queries, and unsupported claims. Unknown likely brands go to `needs_review`.
- Every required product anchor must appear naturally in each variant, either inside an assigned key or in ordinary prose. Missing anchors make the commercial audit fail.
- Unresolved contradictory product facts make the commercial audit fail and block validated descriptions.
- Use the fullest truthful key coverage that still reads naturally. Every variant needs at least two ordinary non-key-led sentences after its SEO block. Use normal Russian syntax, varied sentence length, and concrete facts. Do not force every sentence to repeat a category noun.
- Count all characters including spaces and punctuation. Every variant must fit the configured limit.

If fewer than three eligible keywords remain, report the shortage and do not present validated descriptions.

## Variants

All three variants must sound like finished customer copy. They differ by keyword hypothesis, not by writing quality.

1. `Основной`: the strongest non-nested `core` keys in descending popularity order. This is the lowest-risk publication candidate and the strict implementation of the approved key plan.
2. `Расширенный`: the same `core` plus relevant, non-nested `extension` keys for additional safe coverage, such as another verified attribute or word-order formulation.
3. `Тестовый`: the same `core` plus non-nested `experimental` accepted keys worth testing because they are broader, less popular, or a secondary formulation. Mark them as experimental in the workbook and explain the hypothesis. Never use an unsupported claim merely to make this variant different.

If no safe extension or experimental key exists, do not invent one. Report which variant cannot be validated and why.

## Completion

Return one `.xlsx`. Completion requires a sourced page snapshot, three populated and meaningfully different variants, separate passing technical and commercial statuses, copy-ready text, visible key highlighting, a used-key register by variant, a complete key base with relevance and exclusion reasons, required-anchor coverage, contradiction status, all original source metrics, and successful visual review of every sheet.
