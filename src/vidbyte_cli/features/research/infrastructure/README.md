# Research infrastructure

This package is the only research layer that knows HTTP routes and wire DTOs.

Confirmed from Vidbyte PR #284:

- `POST /research/run`
- `POST /research/threads/{thread_id}/run`
- `POST /research/runs/{run_id}/continue`

The read, capability, and export routes in `routes.py` are forward contract assumptions
approved for CLI implementation before the backend completes them. Keeping them in one
adapter makes later route corrections local.
