# Immediate Next Steps

## Description
An immediate-next-steps suggestion identifies an action the caller can take from the present state. It focuses on reducing the distance between current knowledge and the next useful result. Unlike continuation, it does not assume that an entire existing plan has already been accepted. It may compare several available moves and choose the one with the best immediate information or progress value. The action should be small enough to begin without another round of abstraction. Its completion signal should tell the caller whether to continue, change course, or stop.

## Things to consider
- What is true about the current state?
- Which actions are genuinely available now?
- What move creates the most useful progress?
- What uncertainty would the first step reduce?
- What can be completed without new permission?
- Which dependencies are already satisfied?
- What result determines the following move?
- What should be deliberately left for later?
