The per-response token limit bounds the intended size of each individual model reply. It keeps one generation or critique turn from consuming the workflow's entire budget.

This threshold is not a billing guarantee because an in-flight request may finish beyond it. Smaller values favor concise artifacts, while larger values accommodate richer context and candidate detail.

The limit must be positive whenever it is specified. It applies consistently to generation, critique, and revision responses.
