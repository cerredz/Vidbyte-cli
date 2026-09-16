# Experiment

## Purpose

Run a bounded test that can change an important decision. An experiment trades a small, controlled cost for information that is otherwise expensive or uncertain. The result should be interpretable enough to support a next choice. The test is useful only when its outcome can alter the plan.

## Intent

State the uncertainty, the hypothesis, the smallest test, and the decision each possible result informs. Keep the test reversible and time-bounded whenever the context allows.

## Timing

Use this category before committing significant time, money, scope, or architecture to an uncertain path. Do not delay a straightforward action when the uncertainty is immaterial to the outcome.

## Checks

- Define a measurable result and the threshold or observation that changes the decision.
- Bound the test's duration, resources, and allowed interpretation before it starts.

## Cautions

- Do not call ordinary implementation an experiment unless it answers a named uncertainty.
- Avoid tests whose result cannot distinguish between the available options.
