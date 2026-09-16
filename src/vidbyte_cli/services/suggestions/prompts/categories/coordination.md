# Coordination

## Purpose

Resolve ownership, sequencing, or dependency alignment that prevents multiple contributors from moving coherently. Coordination suggestions reduce duplicated work, waiting, and conflicting assumptions. They should identify the people, agents, or teams involved and the decision that aligns them. The result is a shared commitment or handoff, not a meeting for its own sake.

## Intent

Make the dependency graph and decision boundary explicit. Recommend the smallest communication, assignment, or sequencing decision that lets the relevant work proceed.

## Timing

Use this category when work is blocked or duplicated because responsibilities, order, or interfaces are unclear. Prefer it before parallel work begins or when a dependency changes.

## Checks

- Name the owners, dependency, order, and decision required for alignment.
- Define the shared artifact or acknowledgment that proves coordination is complete.

## Cautions

- Do not recommend coordination when one owner can act without waiting for others.
- If the issue is a missing condition rather than misalignment, use prerequisite instead.
