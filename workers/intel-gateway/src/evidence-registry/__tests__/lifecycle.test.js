import assert from "node:assert/strict";
import { test } from "node:test";
import {
  IllegalLifecycleTransitionError,
  LIFECYCLE_STATES,
  assertValidTransition,
  buildTransitionAuditEntry,
  canTransition,
  getLegalNextStates,
  isTerminalState,
  isValidLifecycleState,
} from "../lifecycle.js";

test("LIFECYCLE_STATES contains exactly the 9 states the spec names, in order", () => {
  assert.deepEqual(LIFECYCLE_STATES, [
    "DRAFT", "COLLECTED", "VALIDATED", "CORRELATED", "PUBLISHED", "UPDATED", "SUPERSEDED",
    "ARCHIVED", "REJECTED",
  ]);
});

test("the full happy-path pipeline is legal end to end", () => {
  const path = ["DRAFT", "COLLECTED", "VALIDATED", "CORRELATED", "PUBLISHED", "UPDATED", "SUPERSEDED", "ARCHIVED"];
  for (let i = 0; i < path.length - 1; i += 1) {
    assert.equal(canTransition(path[i], path[i + 1]), true, `${path[i]} -> ${path[i + 1]} should be legal`);
    assert.doesNotThrow(() => assertValidTransition(path[i], path[i + 1]));
  }
});

test("REJECTED is reachable from every pre-publication state", () => {
  for (const state of ["DRAFT", "COLLECTED", "VALIDATED", "CORRELATED"]) {
    assert.equal(canTransition(state, "REJECTED"), true, `${state} -> REJECTED should be legal`);
  }
});

test("ARCHIVED and REJECTED are terminal  -  no legal outgoing transitions", () => {
  assert.equal(isTerminalState("ARCHIVED"), true);
  assert.equal(isTerminalState("REJECTED"), true);
  assert.deepEqual(getLegalNextStates("ARCHIVED"), []);
  assert.deepEqual(getLegalNextStates("REJECTED"), []);
});

test("illegal transitions are rejected: skipping stages, going backward, leaving a terminal state", () => {
  assert.equal(canTransition("DRAFT", "PUBLISHED"), false, "cannot skip stages");
  assert.equal(canTransition("PUBLISHED", "DRAFT"), false, "cannot go backward");
  assert.equal(canTransition("ARCHIVED", "PUBLISHED"), false, "cannot leave a terminal state");
  assert.equal(canTransition("REJECTED", "DRAFT"), false, "cannot leave a terminal state");
});

test("assertValidTransition throws IllegalLifecycleTransitionError with both states on the error", () => {
  assert.throws(
    () => assertValidTransition("DRAFT", "PUBLISHED"),
    (err) => {
      assert.ok(err instanceof IllegalLifecycleTransitionError);
      assert.equal(err.fromState, "DRAFT");
      assert.equal(err.toState, "PUBLISHED");
      return true;
    }
  );
});

test("assertValidTransition throws a plain Error for an unrecognized state name", () => {
  assert.throws(() => assertValidTransition("NOT_A_STATE", "DRAFT"), /Unknown lifecycle state/);
  assert.throws(() => assertValidTransition("DRAFT", "NOT_A_STATE"), /Unknown lifecycle state/);
});

test("isValidLifecycleState / getLegalNextStates basic contract", () => {
  assert.equal(isValidLifecycleState("PUBLISHED"), true);
  assert.equal(isValidLifecycleState("NOT_A_STATE"), false);
  assert.deepEqual(getLegalNextStates("PUBLISHED"), ["UPDATED", "SUPERSEDED", "ARCHIVED"]);
});

test("UPDATED can self-loop (repeated edits) without forcing a round-trip through PUBLISHED", () => {
  assert.equal(canTransition("UPDATED", "UPDATED"), true);
});

test("buildTransitionAuditEntry returns a frozen entry with the given from/to/reason/actor", () => {
  const entry = buildTransitionAuditEntry("DRAFT", "COLLECTED", { reason: "feed ingested", actor: "system" });
  assert.equal(entry.from, "DRAFT");
  assert.equal(entry.to, "COLLECTED");
  assert.equal(entry.reason, "feed ingested");
  assert.equal(entry.actor, "system");
  assert.ok(entry.at);
  assert.ok(Object.isFrozen(entry));
});

test("buildTransitionAuditEntry defaults reason/actor to null when omitted", () => {
  const entry = buildTransitionAuditEntry("DRAFT", "COLLECTED");
  assert.equal(entry.reason, null);
  assert.equal(entry.actor, null);
});
