# Contracts

`schemas/` is **generated**. Don't edit it by hand.

Source of truth: `backend/src/ftm/contracts/models.py` (pydantic, owner M1).
After a change, run `make contracts`. It regenerates `schemas/*.json` and `frontend/src/types/contracts.ts`. CI fails if they are stale.
