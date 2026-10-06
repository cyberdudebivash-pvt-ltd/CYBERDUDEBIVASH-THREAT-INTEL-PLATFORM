/**
 * Evidence Lifecycle Engine  -  Stage 11 Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Pure, stateless transition-graph validation. Deliberately holds no per-evidence state itself
 * (no Map, no cache)  -  "which state is evidence X currently in" is registry-service.js's job
 * (One Evidence Lifecycle: a single registry instance is the one authority on current state);
 * this module only answers "is transitioning from A to B ever legal," a property of the state
 * machine itself, not of any specific evidence record.
 *
 * Pipeline (forward-progressing, with REJECTED as an escape hatch from any pre-publication
 * state, and ARCHIVED as the terminal state reachable from every post-publication state):
 *
 *   DRAFT -> COLLECTED -> VALIDATED -> CORRELATED -> PUBLISHED -> [UPDATED | SUPERSEDED] -> ARCHIVED
 *     \          \            \             \
 *      -----------+------------+-------------+---------------------------------> REJECTED
 */

export const LIFECYCLE_STATES = Object.freeze([
  "DRAFT",
  "COLLECTED",
  "VALIDATED",
  "CORRELATED",
  "PUBLISHED",
  "UPDATED",
  "SUPERSEDED",
  "ARCHIVED",
  "REJECTED",
]);

const LIFECYCLE_TRANSITIONS = Object.freeze({
  DRAFT: Object.freeze(["COLLECTED", "REJECTED"]),
  COLLECTED: Object.freeze(["VALIDATED", "REJECTED"]),
  VALIDATED: Object.freeze(["CORRELATED", "REJECTED"]),
  CORRELATED: Object.freeze(["PUBLISHED", "REJECTED"]),
  PUBLISHED: Object.freeze(["UPDATED", "SUPERSEDED", "ARCHIVED"]),
  UPDATED: Object.freeze(["UPDATED", "SUPERSEDED", "ARCHIVED"]),
  SUPERSEDED: Object.freeze(["ARCHIVED"]),
  ARCHIVED: Object.freeze([]),
  REJECTED: Object.freeze([]),
});

export class IllegalLifecycleTransitionError extends Error {
  constructor(fromState, toState) {
    const legal = LIFECYCLE_TRANSITIONS[fromState];
    super(
      `Illegal lifecycle transition: ${fromState} -> ${toState}. Legal transitions from ` +
        `${fromState}: [${legal && legal.length ? legal.join(", ") : "none (terminal state)"}]`
    );
    this.name = "IllegalLifecycleTransitionError";
    this.fromState = fromState;
    this.toState = toState;
  }
}

/** @param {string} state @returns {boolean} */
export function isValidLifecycleState(state) {
  return LIFECYCLE_STATES.includes(state);
}

/** @param {string} fromState @returns {string[]} */
export function getLegalNextStates(fromState) {
  return LIFECYCLE_TRANSITIONS[fromState] ? [...LIFECYCLE_TRANSITIONS[fromState]] : [];
}

/** @param {string} fromState @param {string} toState @returns {boolean} */
export function canTransition(fromState, toState) {
  return Boolean(LIFECYCLE_TRANSITIONS[fromState] && LIFECYCLE_TRANSITIONS[fromState].includes(toState));
}

/**
 * Throws IllegalLifecycleTransitionError (or a plain Error for an unrecognized state name) if
 * the transition is not legal. Every registry-service.js mutation that changes lifecycle state
 * calls this first  -  "Every transition must be validated... Illegal transitions must fail."
 * @param {string} fromState @param {string} toState
 */
export function assertValidTransition(fromState, toState) {
  if (!isValidLifecycleState(fromState)) {
    throw new Error(`Unknown lifecycle state "${fromState}"  -  must be one of ${LIFECYCLE_STATES.join(", ")}`);
  }
  if (!isValidLifecycleState(toState)) {
    throw new Error(`Unknown lifecycle state "${toState}"  -  must be one of ${LIFECYCLE_STATES.join(", ")}`);
  }
  if (!canTransition(fromState, toState)) {
    throw new IllegalLifecycleTransitionError(fromState, toState);
  }
}

/** @param {string} state @returns {boolean} */
export function isTerminalState(state) {
  return getLegalNextStates(state).length === 0;
}

/**
 * Builds one immutable audit-trail entry for a transition. Pure function  -  the caller
 * (registry-service.js) is responsible for storing the returned entry; this module holds no
 * state of its own, so the same transition graph can be reused (and independently unit-tested)
 * regardless of how or where transitions end up being recorded.
 * @param {string} fromState @param {string} toState
 * @param {{reason?: string, actor?: string}} [context]
 * @returns {Readonly<{from: string, to: string, at: string, reason: string|null, actor: string|null}>}
 */
export function buildTransitionAuditEntry(fromState, toState, context = {}) {
  return Object.freeze({
    from: fromState,
    to: toState,
    at: new Date().toISOString(),
    reason: context.reason || null,
    actor: context.actor || null,
  });
}
