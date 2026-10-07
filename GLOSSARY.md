# OpenShell teams

Agent teams in which every agent runs in its own OpenShell sandbox, and creating agents and team communication are checked and enforced outside agent-controlled processes.

## People and agents

**User**:
The person who supplies the team boundary and lead policy and approves each proposed team.
_Avoid_: operator, admin (unless meaning a workspace administrator)

**Lead**:
The agent that plans a team and proposes the workers it needs.
_Avoid_: manager, orchestrator, parent (when staffing)

**Worker**:
An agent created by the lead to carry out part of the team's work.
_Avoid_: teammate, member, child (when staffing)

**Sub-agent**:
An agent created by another agent to take over part of that agent's own task (delegation).
_Avoid_: child agent, helper

## Authority

**Team boundary**:
The most any agent on a team may ever have, supplied by the user as a policy plus allowed credential providers and team limits.
_Avoid_: team policy, max policy, envelope

**Lead policy**:
The lead's own sandbox policy, narrower than the team boundary.

**Proposed policy**:
A sandbox policy the lead proposes for one worker, shown to the user and proven inside the ceiling before use.
_Avoid_: AI-written policy, generated policy

**Ceiling**:
What a new agent's grant must fit inside: the team boundary for the lead's workers, the parent's grant for a sub-agent.
_Avoid_: limit, cap, upper bound

**Grant**:
Everything one admitted agent may do: its sandbox policy, credential providers, communication rights and agent-creation rights.
_Avoid_: permissions, policy (when meaning all four parts)

**Staffing**:
The lead creating workers for its team; checked against the team boundary.

**Delegation**:
An agent creating a sub-agent for part of its own task; checked against that agent's grant.

**Approval ID**:
A single-use proof that the user approved one proposed worker, bound to the lead, the team and the exact proposed policy.
_Avoid_: approval token, ticket

**Access rules**:
The harness's own rules for who may do what on its board, by role (for OpenWorker: lead, worker, user).
_Avoid_: communication profile, board permissions

**Approval card**:
The harness's screen on which the user sees and approves a proposed team and its policies before agents are created.

## The six primitives and the harness side

**Team Charter**:
The user-supplied configuration for one team: team boundary, lead policy, and the harness's access rules and endpoint map.
_Avoid_: Team Manifest, team config

**Spawn Gate**:
The admission every new agent passes before it starts: authorize the caller, build and prove the grant, register the agent with the board, then start it.
_Avoid_: admission controller, creation check

**Agent registry**:
The record of which agents exist, their generation and who created whom.
_Avoid_: lineage store

**Policy Lock**:
The rule that no one can widen a running agent's grant or attach new credentials to it.

**Sandbox Passport**:
A signed caller identity, attached outside the agent, that names the calling sandbox and its generation.
_Avoid_: Agent Badge, token, credential

**Channel Guard**:
The per-agent proxy rules that allow only the board operations an agent's role permits.

**Cascade Stop**:
An explicit stop of an agent or team that also stops every agent it created and removes their board access.

**Harness Bridge**:
The harness-side integration that sends creation requests and runs each agent in the sandbox OpenShell creates.
_Avoid_: adapter

## Communication

**Board**:
The harness's own trusted service where agents post, comment, claim and assign work.
_Avoid_: blackboard, forum, Team Log

**Slice**:
The part of the board a worker may see: items assigned to it, items it filed, and items linked to those.

**Agent runner**:
The process that runs one agent inside its sandbox and talks to the host only through its supervisor.
_Avoid_: worker daemon, child runner

**Patcher**:
In the demo team, the worker that changes code in its own worktree.

**Reviewer**:
In the demo team, the read-only worker that checks the patcher's work.

**Generation**:
A counter for each sandbox that changes on restart, so identities from before a restart stop working.
