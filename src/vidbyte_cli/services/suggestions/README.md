# Suggestions service

Local next-action agent: goal plus optional caller context in, ranked ideas with deterministic handoffs out. `service.py` owns the loop shape; `sdk.py` is the only SDK import; generator, critic, and one-file-per-category prompts live in `prompts/`.

`categories.py` owns the 14 exact identifiers and maps each retained category to a packaged Markdown definition under `prompts/categories/`. The `long_term_suggestions` definition covers a 3-6 month capability path and a 2 year+ direction.
