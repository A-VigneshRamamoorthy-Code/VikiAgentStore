import React from 'react';
import {Vector} from '../lib/Vector.jsx';
import traced from '../generated/props.json';

/**
 * Props, replayed from the Python engine's own artwork.
 *
 * Nothing here draws. `tools/trace-props.py` captured every prop *instance*
 * in the board -- with the seed that instance really gets -- across only the
 * axes it responds to, so a prop is selected rather than computed. That is
 * what a limited-animation film does on paper anyway: a small number of
 * discrete drawings, held.
 *
 * The engine drives a prop on two clocks and they are not interchangeable:
 *
 * * `phase` is the drawing clock, quantised with the characters, and its
 *   rate is **zero unless the board gave the prop an `anim`** -- so in this
 *   board every vehicle holds one drawing and the scenery moves past it.
 *   An earlier cut of this file spun the wheels of parked cars, which is
 *   both wrong and the loudest error in a still comparison.
 * * `t` is the shot's true local time, unquantised, for the parts of a prop
 *   that are scenery rather than drawing: a light bar, a rotor, a blinker.
 */

const PHASES = traced.phases;
const T_STEPS = traced.tSteps;
const T_SPAN = traced.tSpan;

export const PROP_BBOX = traced.bbox;

const wrap = (i, n) => ((i % n) + n) % n;

/**
 * @param {string} shot   shot id, so the instance keeps its own seed
 * @param {number} index  position of the prop in the shot's `props` array
 * @param {number} tPose  quantised pose clock, seconds
 * @param {number} tLocal unquantised shot clock, seconds
 */
export const Prop = ({shot, index, tPose = 0, tLocal = 0}) => {
  const inst = traced.instances[`${shot}:${index}`];
  if (!inst) return null;

  const pi = inst.usesPhase
    ? wrap(Math.floor(((inst.phase0 + tPose * inst.rate) % 1) * PHASES), PHASES)
    : 0;
  const ti = inst.usesT
    ? wrap(Math.floor((tLocal / T_SPAN) * T_STEPS), T_STEPS)
    : 0;

  const ops = inst.grid[pi]?.[ti];
  if (!ops) return null;
  return <Vector ops={ops} idPrefix={`p${shot}_${index}_${pi}_${ti}`} />;
};

export const PROP_KINDS = new Set(
  Object.values(traced.instances).map((v) => v.kind)
);
