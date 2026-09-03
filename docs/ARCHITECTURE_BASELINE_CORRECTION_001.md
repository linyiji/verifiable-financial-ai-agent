# ARCHITECTURE_BASELINE_CORRECTION_001

Status: **AUTHORITATIVE**  
Authorized by: User  
Date: 2026-09-03

## Superseded intermediate instruction

- Python 3.14 as the main runtime is void and must not be used for this project.

## Current authoritative baseline

- Main backend runtime: Python `>=3.11,<3.12`
- Web/frontend runtime: Node.js `>=24,<25`

## Reason

The architecture documents and FinRobot compatibility range align with Python 3.11. The project
prioritizes reuse of existing financial logic rather than introducing Python 3.14 compatibility work.

## Reuse policy

Every pre-existing implementation is audited before replacement:

1. `DIRECT_REUSE`
2. `ADAPTER_REUSE`
3. `PORT_REQUIRED`
4. `REPLACE_REQUIRED`

The required engineering order is `REUSE → WRAP → ADAPT → TEST`, not a rewrite driven by the
target directory layout.

FinRobot remains a third-party capability source behind an adapter boundary.
