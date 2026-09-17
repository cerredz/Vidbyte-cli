# Suggestions service

Local next-action agent: goal plus optional caller context in, ranked ideas with deterministic handoffs out. `service.py` owns complete critic-to-generator refinement cycles. The generator keeps one persistent SDK thread, while each fresh critic returns one whole-slate signal block that the SDK context manager places at the end of the generator conversation. `sdk.py` is the only SDK import; prompts live in `prompts/`.
