The message limit caps how many times critics may message the generator directly during one run. A critic that finds one problem more important than a full review can stop early and send the generator a message, which the generator reads as its next turn in place of that round's review. It accepts zero through eight messages and defaults to two, the same as the default round count, because each critic sends at most one message before it stops.

Once the limit is spent, later critics run without the message tool and always return a full structured review. Zero disables critic messages entirely, so every round ends in a graded review.

The limit does not cover the generator's message to the parent agent. That message ends the run with the needs_input status, so it can happen at most once and needs no separate cap. Values outside the supported range are rejected before model work begins.
