import React from 'react';
import {Composition} from 'remotion';
import {Pursuit} from './Film.jsx';
import {WetPaint} from './wetpaint/WetPaint.jsx';
import camera from './generated/camera.json';

const FPS = camera.fps;
// The traced frame count, not `ceil(end * fps)`. The board's last shot ends on
// a fractional frame, and rounding it up renders one frame the Python engine
// never draws -- which offsets nothing, but does make every frame-indexed
// comparison against the reference render report a phantom extra frame.
const DURATION = camera.total;

export const RemotionRoot = () => (
  <>
    <Composition id="Pursuit" component={Pursuit}
                 durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    {/* The vertical cut is the same component at a different board shape --
        no second timeline, no re-authored staging. */}
    <Composition id="PursuitVertical" component={Pursuit}
                 durationInFrames={DURATION} fps={FPS} width={1080} height={1920} />

    {/* An original short, drawn natively in React rather than traced out of the
        Python engine. It exists to answer a different question from `Pursuit`:
        not "can Remotion replay this style faster" but "can Remotion *be* the
        studio". 24 fps because that is what the reference runs at, and the
        stepped hold that makes a drawing read as drawn is defined against it. */}
    <Composition id="WetPaint" component={WetPaint}
                 durationInFrames={1540} fps={24} width={1920} height={1080} />
  </>
);
