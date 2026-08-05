# Generic polling

`Poller` watches one typed target until terminal state, timeout, or cooperative
cancellation. Targets own status policy and stable fingerprints; observers own progress
presentation. The poller suppresses duplicate transitions and caps server delay hints.

Cancellation stops only local observation. It never infers or sends remote cancellation.
