import React from 'react';
import {Composition} from 'remotion';
import {
  SecondThoughts,
  SecondThoughtsDusk,
  SecondThoughtsFlat,
  DURATION,
} from './films/SecondThoughts.jsx';
import {RigTest, RigPortrait, RIG_DURATION} from './films/RigTest.jsx';
import {AtticScene, ForestScene, CaveScene, CrystalCard} from './films/StoryScenes.jsx';
import {SampleFilm, SAMPLE_DURATION} from './films/SampleFilm.jsx';
import {Crosstown, CROSSTOWN_DURATION} from './films/Crosstown.jsx';
import {DoublingBack, DOUBLING_DURATION} from './films/DoublingBack.jsx';
import {Picnic, PICNIC_DURATION} from './films/Picnic.jsx';
import {HumaaansBench, BENCH_DURATION} from './films/HumaaansBench.jsx';

const FPS = 30;

export const RemotionRoot = () => (
  <>
    <Composition id="SampleFilm" component={SampleFilm}
                 durationInFrames={SAMPLE_DURATION} fps={30} width={1920} height={1080} />
    <Composition id="AtticScene" component={AtticScene}
                 durationInFrames={90} fps={30} width={1920} height={1080} />
    <Composition id="ForestScene" component={ForestScene}
                 durationInFrames={90} fps={30} width={1920} height={1080} />
    <Composition id="CaveScene" component={CaveScene}
                 durationInFrames={90} fps={30} width={1920} height={1080} />
    <Composition id="CrystalCard" component={CrystalCard}
                 durationInFrames={90} fps={30} width={1920} height={1080} />
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

    {/* The second asset pack: Humaaans on the same solver. */}
    <Composition id="Crosstown" component={Crosstown}
                 durationInFrames={CROSSTOWN_DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="CrosstownVertical" component={Crosstown}
                 durationInFrames={CROSSTOWN_DURATION} fps={FPS} width={1080} height={1920} />

    {/* The craft pass: walk, stop, hold, turn, run. Every join in that chain
        is somewhere a rig lies, which is the point of shooting it. */}
    <Composition id="DoublingBack" component={DoublingBack}
                 durationInFrames={DOUBLING_DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="DoublingBackVertical" component={DoublingBack}
                 durationInFrames={DOUBLING_DURATION} fps={FPS} width={1080} height={1920} />

    {/* Four bodies of three builds on one ground plane, and a held beat with
        all of them in it. The opposite exam to DoublingBack. */}
    <Composition id="Picnic" component={Picnic}
                 durationInFrames={PICNIC_DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="PicnicVertical" component={Picnic}
                 durationInFrames={PICNIC_DURATION} fps={FPS} width={1080} height={1920} />

    {/* Not films. The bench every rig change is judged on before it is allowed
        into one. */}
    <Composition id="RigTest" component={RigTest}
                 durationInFrames={RIG_DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="RigPortrait" component={RigPortrait}
                 durationInFrames={RIG_DURATION} fps={FPS} width={1080} height={1350} />

    {/* Proportion control: the artist's own composition beside the rig. */}
    <Composition id="HumaaansBench" component={HumaaansBench}
                 durationInFrames={BENCH_DURATION} fps={FPS} width={2760} height={900} />
  </>
);
