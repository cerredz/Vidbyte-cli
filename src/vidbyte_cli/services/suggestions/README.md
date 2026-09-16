# Suggestions service

Local next-action agent: goal plus optional caller context in, ranked ideas with deterministic handoffs out. Context distinguishes completed facts, active work, and future intended work, so planned work can guide sequencing without being treated as complete. `service.py` owns the loop shape; `sdk.py` is the only SDK import; prompts live in `prompts/`.
