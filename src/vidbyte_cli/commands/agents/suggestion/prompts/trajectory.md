Trajectory context contains the complete observable path taken by the parent agent before requesting suggestions. It may include user turns, agent responses, tool results, decisions, reversals, and unresolved branches in their original order.

Preserving the full path lets the specialized agent understand how the current state emerged rather than seeing only a lossy summary. The trajectory is bounded with the rest of the managed context and remains caller-supplied data.

Trajectory content informs continuity, contradiction detection, and lessons from earlier attempts. Omission means the parent history was not supplied and prevents the agent from claiming it has seen that history.
