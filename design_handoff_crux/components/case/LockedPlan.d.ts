import React from 'react';

export interface LockedPlanProps {
  /** A verdict has been logged — reveal the children (the action plan). */
  unlocked?: boolean;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * Signature element B — the sealed action plan. Until a Verdict is logged,
 * the plan hides behind a hatched, lock-iconed panel ("Locked until you log
 * a verdict"). This makes the 50/50 split literal: crux researches; you test.
 * Never show an action plan on an unverified case.
 *
 * @startingPoint section="Case" subtitle="Sealed until a verdict is logged" viewport="700x180"
 */
export function LockedPlan(props: LockedPlanProps): JSX.Element;
