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

// Colour is NOT set here, deliberately, even though this is where it belongs.
//
// `Config.setPixelFormat('yuv420p')` and `Config.setColorSpace('bt709')` are
// both accepted by this version (4.0.516) and both silently ignored by
// `remotion render` -- verified by reading the generated FFmpeg command, which
// still carried the default full-range JPEG pipeline. The equivalent CLI flags
// do work, so they live in package.json's scripts instead. Moving them back
// here looks tidier and quietly reverts the fix.

