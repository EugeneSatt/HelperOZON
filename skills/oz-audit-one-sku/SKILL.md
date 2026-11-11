---
name: oz-audit-one-sku
description: Audit one Ozon Seller article/SKU through the browser from SEO, content, price and promotions, reviews, availability, and advertising to unit economics, then produce an evidence-based color-scored HTML report. Use when the user requests a full or test audit of one Ozon product in a specified seller cabinet.
---

# Ozon audit for one SKU

Audit exactly one seller article and its matching Ozon SKU. Use the authenticated in-app Browser for Ozon Seller and the public product page. Keep the work read-only: do not change prices, promotions, campaigns, content, stocks, or settings.

## Required pre-audit gate

Before opening or reading product data, ask the user for all of the following in one message:

1. Unit cost in rubles. Treat it as production and packaging cost per saleable unit; ask for clarification only if the user gives several cost figures.
2. Audit interval. Offer the standard choices below with their calculated start and end dates, while allowing a custom interval.
3. Confirmation that the current model is **GPT-5.6 Sol** with reasoning **High**. If another model or reasoning level is selected, recommend switching to Sol High and wait for confirmation before starting the full audit.

Also collect the seller article/SKU and seller cabinet name if they were not supplied in the request. Do not repeat a question already answered in the conversation.

After the gate is complete, proceed through the whole audit without asking for routine confirmations.

### Interval choices to offer

Calculate dates relative to today and exclude the current incomplete day:

- **7 completed days — express audit:** best for recent operational changes, stock, bids, and campaign control; more sensitive to daily noise.
- **28 completed days — recommended full audit:** the default for a complete card audit and comparison with the preceding 28 days.
- **Previous calendar month:** useful for closed management and finance reporting.
- **Custom dates:** use for a promotion, content change, price test, or other known event.

Present the exact dates beside every choice. If the user gives dates directly, accept them without offering the menu again. Do not silently replace 28 days with 30 days.

## Binding and date rules

- Confirm the seller cabinet, seller article, Ozon SKU, product name, and exact variant before collecting metrics.
- Never mix reviews, search results, finance rows, or advertising data from sibling variants. Record both seller article and Ozon SKU in working notes and in the report.
- Use the user's interval wherever the Ozon section allows exact dates.
- Ozon modules may expose different date limits or presets. Record the actual period beside every section; never present unlike periods as one common period.
- Prefer completed days. Mark the current day as incomplete when it is included.
- If exact dates are unavailable in a module, use the closest available preset and disclose the difference.

## Direct Ozon routes

Open these routes directly instead of searching through menus. Replace `{ozon_sku}` and `{product_id}` before navigation. Discover `product_id` once from the product overview or edit URL and reuse it.

- Seller home: `https://seller.ozon.ru/app/dashboard/main`
- Products: `https://seller.ozon.ru/app/products`
- Product overview: `https://seller.ozon.ru/app/products/card-overview/{product_id}`
- Product media and content: `https://seller.ozon.ru/app/products/{product_id}/edit/media`
- Sales funnel: `https://seller.ozon.ru/app/analytics`
- Product sales analytics: `https://seller.ozon.ru/app/analytics/graphs`
- Search analytics for the exact SKU: `https://seller.ozon.ru/app/analytics-search/search-results/my-products/{ozon_sku}`
- Prices and product promotions: `https://seller.ozon.ru/app/prices/control`
- Advertising overview: `https://seller.ozon.ru/app/advertisement/product/overview`
- FBO availability: `https://seller.ozon.ru/app/analytics/supply/goods-availability/index`
- Finance accrual details: `https://seller.ozon.ru/app/finances/accruals?tab=ACCRUALS_DETAILS`
- Unit economics: `https://seller.ozon.ru/app/finances/accruals?tab=UNIT_ECONOMY`
- Public product reviews for the exact variant: `https://www.ozon.ru/product/{ozon_sku}/?tab=reviews&reviewsVariantMode=1`

Reuse open tabs and filter by the exact seller article or SKU inside each page. Do not browse the public web to rediscover Seller routes unless a listed route no longer works.

## Browser audit

Collect evidence from these areas, adapting navigation to the current Ozon interface:

1. **Identity and availability:** product overview, FBO/FBS stocks, days without stock, recommended supply, delivery availability by important buyer locations, and any Ozon availability warning.
2. **Sales funnel:** impressions, search/catalog impressions, product visits, cart additions, orders, buyouts, revenue, average realized price, stage conversions, and change versus the comparison period.
3. **SEO:** exact SKU in search analytics; query demand, position, search-to-card conversion, search-to-order conversion, orders, and revenue. Compare the important query phrases with the current title and identify exact, partial, and missing coverage.
4. **Content:** title, first image, remaining media, rich content, description, composition, characteristics, and content score. Flag contradictions, grammar and typography errors, unclear claims, and claims that need evidence.
5. **Price and promotions:** site price, current seller price where shown, price index, competitor price, active promotions, future promotions, and eligibility. For each relevant promotion, search the exact article in the “add products” list. Distinguish “can join,” “already participating,” and “cannot join.” Do not join a promotion.
6. **Advertising:** every campaign containing the exact SKU. Capture spend, attributed sales, units, DRR, CPC, CPO, CTR, and campaign type for the closest permitted period.
7. **Reviews:** open the public product page, select “this product variant,” and analyze only 20 reviews. Use a pure newest-first sort if offered. Otherwise analyze the 20 top reviews Ozon displays under its current “new and useful” sort and state that limitation. Classify positive, mixed, and negative sentiment; count repeated themes; identify purchase triggers, objections, quality signals, and whether reviews support the advertised product functions.
8. **Unit economics:** use `Finances → Store economics → Unit economics` for the exact SKU and closest available period. Capture delivered units, sales, Ozon commission, acquiring, delivery and placement, returns, additional services, promotion, and Ozon profit before unit cost. Add the user-supplied unit cost outside Ozon's table when the cabinet has not stored it.

For detailed metric interpretation, formulas, and score anchors, read [references/audit-method.md](references/audit-method.md).

## Evidence and calculations

- Use values visible in Ozon. Do not invent a commission, logistics charge, tax rate, eligibility reason, review count, or period.
- Compute unit economics from financial accruals divided by delivered units, not from the advertising CPO.
- Explain any difference between campaign CPO and the finance line for total promotion.
- Report profit before tax when the user's tax regime is unknown. A tax scenario may be added only when clearly labeled as conditional.
- Cross-check totals and unit values before writing the report.
- Treat Ozon's content score as completeness, not proof that claims are accurate or that content converts well.
- Treat attributed advertising sales as an Ozon attribution metric, not proof of incremental sales.

## AI assessment

Score these blocks from 0 to 10 and give one evidence-based sentence for each:

- overall readiness for growth;
- SEO;
- content and conversion;
- price and promotions;
- reviews and quality;
- availability and logistics;
- advertising;
- unit economics.

Color scores consistently in the HTML:

- green for 7.0–10.0;
- amber for 5.0–6.9;
- red for 0–4.9.

Scores must follow the evidence anchors in the method reference. Do not copy scores from a previous SKU.

## HTML report

### Required report palette

Use the light paper palette for every full SKU audit HTML report. Set the page background to paper #F1EBE2, table and card surfaces to warm white #FCF9F3, primary text to ink #20211E, and muted text to #625F58. Use sky blue #A8CEDF for table headers and the product cover panel, pink #EDA4B9 for the main metrics strip, and lime #DFED68 for highlights and the key warning. Embed these colors in the self-contained HTML.

Keep the score legend and semantic score colors visible within the light palette: green #226243 for 7.0–10.0, amber #755112 for 5.0–6.9, red #8B2444 for 0–4.9, and muted #625F58 for insufficient data.


Create a responsive, self-contained HTML file at:

`<workspace>/outputs/ozon-audit-<seller-article>-<audit-date>.html`

Use a clear executive layout with:

- product identity, seller cabinet, audit date, and the main period at the top;
- the main conclusion and highest-risk warning;
- color-coded AI scores and their legend;
- prioritized P0/P1/P2 actions;
- sales funnel, SEO/title comparison, content errors, promotions, advertising, 20-review analysis, and unit economics;
- formulas or calculation tables needed to reproduce financial conclusions;
- actual periods, sources, and limitations.

Lead with the operational constraint that most limits growth. Keep recommendations tied to measured evidence. If availability or unit economics is critical, do not recommend scaling ads or adding discounts until the report shows the condition that would make scaling viable.

Open the finished report in the in-app Browser. If direct `file:` navigation is blocked, serve the `outputs` folder on localhost and open the local HTTP URL. Visually inspect the full page for clipping, unreadable tables, broken characters, and incorrect score colors before completing the task.

## Completion

Return the HTML file link and state the main commercial conclusion, review-sample result, and profit per delivered unit before tax. Mention material period limitations. Do not ask for approval after the report is complete because the audit is read-only.
