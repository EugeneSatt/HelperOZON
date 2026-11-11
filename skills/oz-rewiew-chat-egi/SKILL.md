---
name: oz-rewiew-chat-egi
description: "Process Ozon Seller buyer reviews rated 4–5 by article/SKU and user-specified dates through Chrome and Computer Use: freeze the requested review batch, preserve the product binding, and send two supplied chat messages in order. Use when the user provides article-message pairs in text or Excel."
---

# OZ Rewiew Chat EGI

Automate a repeatable Ozon Seller workflow for sending two user-provided chat messages, in order, to buyers associated with reviews of specified articles. Only 4- and 5-star reviews within the user's date range are eligible. The review-to-chat product context is part of the task and must be verified before sending.

## Input

- Accept article/SKU plus a first and second message from the user's message.
- If an Excel file is provided, read each row as an article/SKU plus two ordered message fields. Preserve the exact article text and message text; trim surrounding whitespace but do not rewrite either message.
- Exactly two messages are required for every article. If the user provides only one message, do not open Ozon reviews or chats; ask them to provide both the first and second messages. Do not infer, split, duplicate, or draft a missing second message.
- If the skill is launched without articles or messages, ask first: which articles/SKUs to process and which first and second messages to send for each article. If an article is missing either message, ask for the missing message before opening chats.
- If several message pairs are supplied for one article, ask how they map to reviews before proceeding.
- Always process only 4- and 5-star reviews. Never include 1-, 2-, or 3-star reviews.
- A date or date range is required. If the user did not specify dates, ask for the date or date range first and do not open reviews or chats until the dates are provided.
- Interpret dates in the user's stated timezone when provided; otherwise use the Ozon cabinet's displayed dates and state the interpretation if it could affect the batch.

## Batch snapshot

- Resolve the requested scope before opening chats: article/SKU, allowed rating (4–5 only), mandatory date range, sort order, freshness, and count (for example, “the first three 5-star reviews from 1–15 August”).
- At discovery time, freeze the selected reviews into a batch. Record the review UUID when visible, article/SKU, product name or URL, buyer, rating, review text, review date/time, and order when visible.
- Do not silently replace a frozen review with a newer review if the list changes during the run. If the requested scope cannot be determined, stop and ask instead of guessing.

## Required browser and computer tools

- Work only in the authenticated Ozon Seller cabinet through Google Chrome and Computer Use.
- Use `chrome:control-chrome` for Chrome navigation, tabs, page state, and browser interaction. Use `computer-use:computer-use` for direct Mac UI actions, visual verification, window focus, and clicks or typing when needed.
- Do not use the in-app browser or substitute another browser, API, direct HTTP request, or terminal-driven Ozon interaction. If Chrome or Computer Use is unavailable, stop and report the limitation.

## Close the AI assistant before buyer-chat actions

- After opening or switching to any Ozon page, check whether the panel «Здравствуйте, я Умный ассистент» / «Найду ответы на ваши вопросы» is open.
- If it is open, close it yourself using the panel's close button. If needed, bring Chrome to the foreground and use `Escape`, then re-check the page state.
- Do not inspect, fill, or send from the assistant field «Задайте вопрос» and do not click its send arrow. Only continue after verifying that the assistant panel and its input are gone and the buyer composer «Вы пишете покупателю» is available.
- If the panel cannot be closed or the UI remains ambiguous, stop that item without sending and report the blocker.

## Browser workflow

For each article–message-pair set:

1. Open «Отзывы покупателей».
2. Filter/search by the article or SKU. Apply the mandatory user-specified date range and restrict ratings to 4 and 5 stars; apply any requested sort or count filters.
3. Freeze the requested reviews from the visible result list before opening chats. Click the review text in the «Отзыв» column (not the product title) to open the review modal.
4. Verify the modal's article/SKU, buyer, rating, date/order, review text, and review UUID when visible. Use «Написать в чат» to open the buyer chat from that exact review.
5. Preserve the chat context created by «Написать в чат». Do not reconstruct or manually navigate to a normalized `/app/messenger` URL, open a different conversation, or use «Ответить на отзыв» as a substitute.
6. Handle Chrome tabs explicitly. Inspect the current Chrome tabs and any user-owned tabs available through the browser connection; use the exact tab opened by the review CTA and wait for it to load. Never assume that a URL or the left chat list identifies the intended conversation.
7. If the chat has a left conversation list, select the frozen buyer only when necessary, then re-check the right panel. The right-panel buyer must match the modal, and the visible product/review card must match the frozen article/SKU. If either check fails or the card disappears, block the item without sending.
8. Check the selected buyer/review chat for the exact ordered pair of messages. If either supplied message is already present in that same context, mark the item skipped; otherwise insert the first message into the composer without changing the product/review card.
9. Send the first message, verify that it appears as sent in the same chat, then send the second message and verify that it appears as sent. **STRICTLY: send both supplied messages in the buyer's chat without preliminary confirmation.** Do not pause for a batch confirmation or ask the user to approve either message.
10. After the send action, run the mandatory post-send verification below. A successful click or temporary success indicator is not enough to mark the item sent.

## Mandatory post-send verification

- Wait for the chat UI to settle, then verify in the same Chrome tab that the buyer chat still exists, the right-panel buyer is unchanged, both exact messages appear as sent in the required order, and the expected product/review card is still visible.
- Re-read the conversation after a refresh or controlled re-open when necessary. Both messages must remain visible after the chat state is reloaded; do not rely only on a toast, button state, or the fact that the send action completed.
- Mark the item `sent` only when both messages and the product/review context are confirmed. If the chat disappears, either message is absent, or the product card is gone/mismatched, mark it `removed_or_unverified` and record that Ozon may have removed the chat or message as spam.
- Never automatically resend a `removed_or_unverified` item. Report it for review so a duplicate message is not created if Ozon delayed or partially processed either send.

## Defaults and safeguards

- Process all matching 4- and 5-star reviews within the user-specified date range for each supplied article, one buyer at a time, unless the user gives a narrower count or scope.
- If dates are missing, ask for them before any Ozon navigation or chat action. Do not infer “today”, “recent”, or another date range.
- For “first N”, “fresh”, or similar requests, use the current visible sort/filter order at discovery time and process exactly the frozen N reviews.
- Do not send to the same buyer/review when either of the exact supplied messages is already present in that chat; report it as skipped.
- Never substitute a product review reply for a buyer chat message. The requested destination is the buyer chat opened from the review modal, with its product/review card preserved.
- If the article search returns no reviews, the buyer chat cannot be opened, the buyer cannot be matched, the product card is missing/mismatched, the tab owner is unclear, or the page state is ambiguous, stop that item and report it without guessing.
- Keep a result log: article/SKU, review UUID, rating, review date or order when visible, buyer, status (sent/skipped/blocked/removed_or_unverified), product-card verified (yes/no), first and second message visibility after reload (yes/no), message timestamps when sent, and reason for any exception.
- Do not upload, download, edit, delete, or change Ozon settings unless the user separately requests it.

## Excel handling

When the user supplies an `.xlsx`, `.xls`, `.csv`, or `.tsv`, use the spreadsheet workflow available in the environment to inspect the workbook and identify the article and template columns. If column names are unclear or multiple sheets contain plausible pairs, ask which sheet/columns to use. Do not alter the source file.
