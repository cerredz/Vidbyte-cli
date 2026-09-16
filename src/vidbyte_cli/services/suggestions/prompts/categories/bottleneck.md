# Bottleneck

## Purpose

Relieve the constraint that limits useful progress. A bottleneck is the narrowest part of the current flow, so improving unrelated areas will not materially accelerate the goal. The suggestion should describe the constraint and the mechanism by which removing it increases throughput or reduces waiting. It should be concrete enough to test against the current process.

## Intent

Locate the limiting resource, decision, dependency, or queue rather than listing every inconvenience. Prefer an action that expands capacity at the point where work is actually accumulating.

## Timing

Use this category when progress repeatedly waits on the same constraint or when effort is being spent faster than the limiting step can absorb it. Reassess after the constraint changes because the bottleneck may move.

## Checks

- Name the observable constraint and quantify its effect in time, capacity, or waiting.
- Explain why the proposed action affects the limiting step instead of a nearby symptom.

## Cautions

- Do not use this category for a plausible risk with no observed constraint.
- Avoid expensive optimization before confirming that the identified step is truly limiting.
