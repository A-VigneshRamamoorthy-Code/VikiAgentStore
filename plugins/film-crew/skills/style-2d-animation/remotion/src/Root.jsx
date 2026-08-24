import React from 'react';
import {Composition} from 'remotion';
import {
  SecondThoughts,
  SecondThoughtsDusk,
  SecondThoughtsFlat,
  DURATION,
} from './films/SecondThoughts.jsx';
import {RigTest, RigPortrait, RIG_DURATION} from './films/RigTest.jsx';

const FPS = 30;

export const RemotionRoot = () => (
  <>
    <Composition id="SecondThoughts" component={SecondThoughts}
                 durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="SecondThoughtsVertical" component={SecondThoughts}
                 durationInFrames={DURATION} fps={FPS} width={1080} height={1920} />

    {/* The same board in the other two packs. Nothing is re-staged: a pack is
        a palette and a set treatment, not a different film. */}
    <Composition id="SecondThoughtsDusk" component={SecondThoughtsDusk}
                 durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="SecondThoughtsFlat" component={SecondThoughtsFlat}
                 durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />

    {/* Not films. The bench every rig change is judged on before it is allowed
        into one. */}
    <Composition id="RigTest" component={RigTest}
                 durationInFrames={RIG_DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="RigPortrait" component={RigPortrait}
                 durationInFrames={RIG_DURATION} fps={FPS} width={1080} height={1350} />
  </>
);
