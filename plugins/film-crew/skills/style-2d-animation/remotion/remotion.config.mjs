import {Config} from '@remotion/cli/config';

// Software rasterisation, deliberately. The default ANGLE backend never
// completes its DevTools handshake on this project's macOS setup -- the render
// dies on "Timed out after 25000 ms while trying to connect to the browser"
// with Chrome having logged nothing at all, which reads like a missing binary
// and is not one. `chrome-headless-shell --screenshot` works fine from the
// command line, so the browser is healthy; it is the GL backend that hangs.
// swiftshader costs some speed and buys a render that actually finishes.
Config.setChromiumOpenGlRenderer('swiftshader');

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
