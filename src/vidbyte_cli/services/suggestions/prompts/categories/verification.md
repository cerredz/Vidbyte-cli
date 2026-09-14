# Verification

## Description
A verification tests a consequential claim about requirements, implementation, assumptions, or results. It turns plausible confidence into inspectable evidence.

## Goal
Resolve whether a claim is true and state what changes when the check fails.

## Intent
Use this type when proceeding without evidence could conceal a meaningful defect or mistaken premise.

## Timeline
Verify before irreversible decisions and before claiming completion. Lower-impact checks may follow the primary delivery when recovery remains easy.

## Checklist
- State the exact claim under test.
- Choose a deterministic or authoritative check.
- Define pass, fail, and follow-up outcomes.

## Cautions
Do not substitute a narrow check for a broad claim. Avoid tests that merely repeat the implementation's own assumptions.
