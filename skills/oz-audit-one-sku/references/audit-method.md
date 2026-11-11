# Audit method

Use this reference while calculating and scoring a one-SKU Ozon audit.

## Period handling

Keep a period ledger in working notes:

| Area | Requested period | Actual Ozon period | Incomplete day | Comparison period |
|---|---|---|---|---|
| Sales funnel | | | | |
| Search analytics | | | | |
| Advertising | | | | |
| Unit economics | | | | |
| Reviews | n/a | review dates | n/a | n/a |

Use the requested period as the report's main period only when the sales funnel matches it. Show the actual period in every section heading or note.

## Unit-economics formulas

Let `D` be delivered units during the finance period.

- Revenue per delivered unit = sales total / `D`.
- Commission per unit = Ozon commission / `D`.
- Acquiring per unit = acquiring / `D`.
- Delivery and placement per unit = delivery and placement / `D`.
- Returns per unit = return costs / `D`.
- Additional services per unit = additional services / `D`.
- Promotion per unit = all promotion and advertising accruals / `D`.
- Platform and promotion cost per unit = sum of all preceding Ozon expense lines.
- Profit before tax per unit = revenue per unit − platform and promotion cost per unit − user-supplied unit cost.
- Margin before tax = profit before tax per unit / revenue per unit × 100%.
- Break-even promotion per unit = revenue per unit − non-promotion Ozon costs per unit − unit cost.
- Promotion ceiling for target margin = revenue per unit − non-promotion Ozon costs per unit − unit cost − target profit per unit.

If the user did not state a target margin, show break-even and a labeled 10% margin scenario. Do not apply a tax without knowing the company's tax regime and tax base.

Reconcile the table total to Ozon's displayed profit before unit cost, allowing only rounding differences. If it does not reconcile, investigate missing columns, credits, partner programs, or bonus points before drawing a conclusion.

## Review coding

Bind the public review list to the exact variant. Analyze 20 review texts and keep a simple evidence table with reviewer/date, sentiment, and themes. Count a theme only when the review text supports it.

Use three sentiment classes:

- positive: the purchase is clearly endorsed and no material objection dominates;
- mixed: it contains meaningful praise and a meaningful objection, or validates only part of the advertised use;
- negative: it rejects the product, says it will not be repurchased, or describes a material defect without offsetting endorsement.

Report the count and percentage for each class. Separate product issues from delivery and packaging issues. Explicitly test whether reviews support important title or image promises such as “2 in 1,” “3 in 1,” long-lasting scent, dispenser convenience, or use as shampoo.

## Score anchors

Scores are diagnostic and must cite the facts that drive them. Use one decimal only when the evidence supports that precision.

### SEO

- 9–10: strong positions and conversion across both broad and exact high-demand queries; title covers intent cleanly.
- 7–8.9: strong exact-query coverage with a visible gap in broad queries or declining conversion.
- 5–6.9: partial semantic coverage, weak positions, or material conversion decline.
- 0–4.9: product is largely invisible, mismatched to query intent, or not indexed for core demand.

### Content and conversion

- 9–10: consistent title/media/description, strong card-to-cart conversion, and supported claims.
- 7–8.9: strong conversion or completeness with limited contradictions or missing proof.
- 5–6.9: several inconsistencies, weak media, or average conversion.
- 0–4.9: misleading contradictions, serious content omissions, or very weak conversion.

### Price and promotions

- 9–10: favorable price index, healthy realized price, suitable active promotions, and protected margin.
- 7–8.9: competitive price and useful promotions with manageable gaps.
- 5–6.9: neutral or unstable price position, unclear promotion value, or excessive promotion exposure.
- 0–4.9: uncompetitive price or discounts that make economics structurally unprofitable.

### Reviews and quality

- 9–10: high rating and buyout, large credible review base, and the 20-review sample has few material objections.
- 7–8.9: generally strong reputation with one recurring product objection.
- 5–6.9: mixed sentiment or multiple recurring quality objections.
- 0–4.9: low rating, weak buyout, or frequent material defects.

### Availability and logistics

- 9–10: adequate multi-cluster cover and stable delivery with no meaningful out-of-stock period.
- 7–8.9: adequate cover with a limited cluster gap.
- 5–6.9: fewer than about 14 days of cover or uneven regional availability.
- 0–4.9: current unavailability, repeated days without stock, or less than about 7 days of cover.

### Advertising

- 9–10: efficient campaigns with stable or improving CTR/CPO/DRR and economics that permit scaling.
- 7–8.9: efficient attributed metrics with a limited decline or unresolved incrementality.
- 5–6.9: mixed campaign efficiency or finance-level promotion costs close to the profit ceiling.
- 0–4.9: advertising is unprofitable, poorly attributed, or consuming the available contribution margin.

### Unit economics

- 9–10: margin before tax at least 25% after all measured variable costs.
- 7–8.9: margin 15–24.9%.
- 5–6.9: margin 8–14.9%.
- 3–4.9: positive margin below 8%.
- 0–2.9: zero or negative margin before tax.

### Overall readiness

Use these weights:

- availability and logistics: 20%;
- SEO: 15%;
- content and conversion: 15%;
- advertising: 15%;
- unit economics: 15%;
- price and promotions: 10%;
- reviews and quality: 10%.

Calculate the weighted mean. A critical availability or negative unit-economics result must also appear in the main conclusion even when the weighted mean is moderate.

## Decision priorities

- P0: an issue that blocks sales, creates losses, or makes new traffic wasteful.
- P1: a material conversion, claim, or promotion issue to fix after P0.
- P2: an optimization or controlled test after stock and economics are stable.

Do not recommend simultaneous changes to price, promotion, media, and advertising when a controlled sequence can identify the effect.
