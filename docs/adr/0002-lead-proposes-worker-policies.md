# The lead proposes each worker's policy; no role profiles

The user supplies only a team boundary and a lead policy; the lead proposes each worker's sandbox policy, the harness shows it on its approval card, and Spawn Gate admits it only if the prover shows it fits inside the boundary. We dropped user-approved role profiles and staffing grants because users would have to write and maintain a profile per role, and board rights already come from the harness's own role rules.

## Consequences

- The prover proves containment, not least privilege; the approval card is the human check.
- Proposals must reuse the boundary's own paths, or the prover returns "unsupported" and Spawn Gate rejects them.
