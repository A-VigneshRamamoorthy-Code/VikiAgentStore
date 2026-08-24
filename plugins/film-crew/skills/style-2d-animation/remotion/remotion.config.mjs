import {Config} from '@remotion/cli/config';

// SwiftShader, not the host GPU. A headless Chrome falling back to a real GPU
// renders subtly differently between machines, which turns any frame-by-frame
// comparison against a previous render into noise.
Config.setChromiumOpenGlRenderer('swiftshader');
Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
