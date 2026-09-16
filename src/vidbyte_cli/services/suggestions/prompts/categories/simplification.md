# Simplification

## Purpose

Remove scope, complexity, or effort while preserving the essential outcome. A simplification makes the path easier to operate, explain, test, or maintain. It should name what disappears and what value remains. The best simplification changes the minimum necessary surface.

## Intent

Find an unnecessary requirement, layer, branch, dependency, or deliverable that can be cut without weakening the goal. Prefer removal over adding another mechanism to manage existing complexity.

## Timing

Use this category when the current plan is too large for its value, when complexity creates recurring cost, or when a smaller release would answer the important question. Apply it before more complexity is committed.

## Checks

- State the preserved outcome and the exact scope or mechanism removed.
- Identify the behavior that proves the simplified version still serves its purpose.

## Cautions

- Do not simplify by deleting a true prerequisite or acceptance condition.
- If the main issue is choosing among routes, use an alternative or strategy category.
