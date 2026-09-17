# Suggestion refinement

Reconsider the complete candidate slate for the goal below using the independent critic signal context supplied with this turn.
Treat that context as useful evidence from another agent rather than a verdict or field-level repair order.
Use your own judgment to preserve strong work, revise weak work, merge overlap, remove poor directions, reorder the slate, or add a materially better candidate.
Return a complete replacement slate of up to {{count}} candidates, including unchanged candidates that still belong.
Keep the existing `idea_id` for every retained or revised candidate, and use a null `idea_id` only for a genuinely new candidate.
Do not invent an identifier, reuse an identifier for a different idea, or cite evidence absent from the caller context.
Return only the structured candidate artifact expected by the caller.

Goal: {{goal}}
