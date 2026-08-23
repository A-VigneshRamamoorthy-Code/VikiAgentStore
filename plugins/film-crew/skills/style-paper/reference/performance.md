# Performance

Where the renderer's time actually goes, and the case for and against moving
compositing onto the GPU. Read [`architecture.md`](architecture.md) first —
this assumes the pipeline order and the determinism principle it describes.

---

## Where the time actually goes

The numbers below come from a real production board: 1920×1080 at 30 fps,
206 elements (1 `card`, 156 `art`, 49 `chip`), 951 seconds of running time —
28,530 frames. Machine: Apple M2, **four performance cores plus four
efficiency cores, 8 GB of memory**, macOS, Python 3.14.6, Pillow 12.3.0,
ffmpeg 8.1.2. That split and that memory ceiling both turn out to matter —
see [What was optimised](#what-was-optimised), where treating the machine as
"eight cores" made the render *slower*. Building that board once — resolving
the storyboard, generating every piece of procedural artwork, baking the
static layer — costs 37.5 s and happens a single time regardless of the
film's length. Rendering it frame by frame, with no profiler attached, cost
195 ms a frame, which is the difference between a nine-minute short and the
~2.65 hours this board took to encode in full.

A profiler changes those numbers — cProfile's own bookkeeping runs at
roughly 3.6× the unattended cost on this renderer — but not their shape. Two
hundred and ten profiled frames, with the one-time board build subtracted
out, split like this:

| Item | ms/frame (profiled) | Share |
|---|---|---|
| `ImagingCore.transform` (PIL rotate) | 292 | 41% |
| `compose` own Python + numpy | 96 | 13% |
| `ImagingCore.resize` (PIL scale) | 87 | 12% |
| `ImagingCore.convert` | 42 | 6% |
| `gaussian_blur` (drop shadows) | 26 | 4% |
| `alpha_composite` | 26 | 4% |
| numpy `_clip` | 20 | 3% |

Those shares add to 83%, not 100% — cProfile is spending the remainder on
call overhead too fine-grained to attribute by name — so back-solving each
row against its own share (292 ⁄ 0.41, 96 ⁄ 0.13, and so on) gives seven
independent estimates of the same profiled-frame total, spread between 650
and 738 ms and averaging close to 692 ms. Divide that average by the ~3.6×
profiler tax and it lands on 192 ms, which is the unattended 195 ms/frame
figure above to within two per cent. Two measurements taken by unrelated
methods agreeing that closely is the reason to trust this table, even
though its own rows do not obviously sum to one.

**Root cause of the top line.** Rotation alone is 41% of the profile — more
than resize, convert, blur and compositing combined — and it traces to a
single element. The board carries exactly one full-bleed backdrop: a `card`
1900×1209 design units, 2.48 megapixels once composited as RGBA, and that
card never sits still. Every loose element on the board carries a continuous
idle wobble: `motion.transform()` (`motion.py`, line 77) is called every
frame with whatever scale, rotation and opacity the element's current
animation state produces, and `idle_float()` (`motion.py`, line 188) is what
supplies that state once an element has finished entering. Its rotation
amplitude defaults to `rot_amp = 0.16`, so the backdrop's entire sweep is
0.32 degrees end to end — under two thousandths of a degree between
consecutive frames at 30 fps, well below what an 8-bit-per-channel image can
render as a visible difference. `transform()` only skips work when a
parameter sits within 1×10⁻³ of its identity value, so a wobble roughly two
orders of magnitude smaller than that threshold still trips a full LANCZOS
resize and a full BICUBIC rotate, at 2.48 megapixels, thirty times a second.
None of the other 205 elements are remotely this size — the next-largest
class, `art`, is a procedural cut-out sized to its own silhouette, not to the
frame — so one element's transform cost is the plurality of the whole
frame budget for a reason that has nothing to do with a defect in the
entrance system and everything to do with paying a full-canvas resample for
a wobble nobody could see if it were skipped.

Two smaller points are worth having in view before the next section. First,
`ImagingCore.resize`'s 87 ms is not all the backdrop card either:
`apply_camera()` (`motion.py`, line 154) crops a window out of the
oversized board and resizes it to the output frame unconditionally, every
frame, regardless of what any individual element is doing, so some of that
line is the camera's own per-frame resample rather than the card's. Second,
the renderer already caches each element's drop shadow on a quantised
elevation key (`Element.shadowed`, in `render.py`), which is why
`gaussian_blur` is only 4%: it is paid for by scraps mid-entrance, not by
the several hundred elements sitting idle. Rounding a continuously varying
parameter to a coarse step so that visually identical frames share one
cached bitmap is exactly the idea behind the fix under way for the
rotate/resize line too; see [the next section](#what-was-optimised) once it
lands.

**The encoder.** Per-frame grain defeats most of x264's own compression, so
the stream is bitrate-capped rather than left to CRF alone, and the encode
is correspondingly heavy. Measured on this board at 1080p, preset `medium`,
`crf 20`: x264 manages 9.8 fps using its own internal multithreading across
roughly 3.4 cores, or 6.06 fps confined to a single thread — 102 ms/frame
against 165 ms/frame. That is faster in wall-clock terms, but not
efficiently so: (9.8 ⁄ 6.06) ⁄ 3.4 is a parallel efficiency of about 48%,
meaning the multithreaded run spends roughly twice the total CPU-seconds per
frame (3.4 cores × 102 ms ≈ 347 core-ms) that the single-threaded run does
(165 core-ms) to buy back 63 ms of wall-clock. That is the ordinary shape of
a codec that parallelises by slicing the picture into per-thread regions —
each extra thread helps less than the last — and it carries a sharper cost
here: x264 divides its search between threads by row or slice, so the
encoded bitstream is a function of how many threads it was given, not only
of the pixels. Two runs of the same encoder settings on the same frames
produce different files if the thread count differs.

**How the renderer spends cores.** The frame range is cut into contiguous
segments — sized from the running time and frame rate, not from the number
of workers available, specifically so the same storyboard cuts into the
same segments whether it renders on a four-core laptop or a sixty-four-core
server — and each segment is handed to its own worker process, which
composes that segment's frames and pipes them, one at a time, into its own
dedicated ffmpeg encoder pinned to a single thread. Composing and encoding
therefore happen across every worker concurrently, but within any *one*
worker they still run in series for that worker's own frames: it writes a
finished frame to its own ffmpeg's standard input, and that call only
returns once there is buffer room for it. Pinning each segment's own encoder
to a single thread costs nothing next to the multithreaded case above,
because the parallelism has already moved from threads inside one x264
process to many independent x264 processes running side by side — which is
also what keeps the output reproducible at any worker count, since every one
of those processes sees the same thread count regardless of how many run at
once.

---

## What was optimised

Four changes, in descending order of what they were worth. Every number here
was measured on the machine described above, rendering a real 24,119-frame
film — not projected from a model.

### 1. One element was half the render

`motion.transform` was called roughly 1.8 times per frame, which is a very
small number of very large images. Instrumenting it found a single element
responsible: the full-bleed backdrop `card`, 1900×1209 design units — 2.48
megapixels of RGBA — LANCZOS-resized and then BICUBIC-rotated **every frame**,
at about 166 ms. It was doing that to render an idle wobble whose entire sweep
is 0.32° (`idle_float` uses `rot_amp=0.16`), i.e. under 0.002° of change
between one frame and the next.

`Element.transformed()` memoises that work, on the same pattern as the existing
`Element.shadowed()` elevation cache. The load-bearing detail is that the key
is quantised **and `M.transform` is called with the quantised values, never the
raw ones**. Keying on a rounded value while computing from an exact one would
make a frame's pixels depend on which frame the worker reached first, and the
render would stop being reproducible the moment work was divided differently.

Serial cost per frame: **195 ms → 87 ms, 2.24×**, with an identical
frame-difference profile.

### 2. The parent was a funnel, so each worker got its own encoder

The old `-j` composed frames in workers and pickled each finished frame — 6.2
MB of raw RGB — back to the parent, which fed one ffmpeg. That is around 136 GB
of inter-process traffic per film through a single pipe, which is why eight
workers only ever bought about 2×.

Measuring the encoder decided the replacement: x264 at `medium`, 1080p, on
grain, runs 9.8 fps while using ~3.4 cores, and 6.06 fps pinned to one thread.
A single shared encoder therefore caps the whole pipeline near 10 fps no matter
how fast compositing becomes — so the encoder had to be replicated, not fed
faster. The timeline is now cut into contiguous segments, each worker composes
and encodes its own to its own file, and the parts are joined with `-c copy`.
No raw frame ever crosses a process boundary.

Reproducibility survives this because the boundaries are a pure function of
`(n_frames, fps)` — never of the worker count or the machine — because x264 is
pinned to `-threads 1` (its bitstream otherwise depends on how many threads
sliced the picture), and because `jobs == 1` runs through the *same* segment
path rather than a separate serial loop. Verified by SHA-256: `-j 1` and `-j 4`
produce byte-identical files.

### 3. `-shortest` was silently eating frames

Adding a frame-count assertion to the join immediately caught 685 frames where
688 were expected. `-shortest` truncates the *video* to the length of the
audio, and the mastered track lands a rounding error short. Isolated with a
synthetic two-segment test: 60 frames in, 55 out. `-af apad -shortest` pads the
audio so the video is the shorter stream again, and the cut lands on the last
frame: 60 in, 60 out.

This was **pre-existing**. The old single-pass encoder used bare `-shortest`
too, so any film whose mastered track landed short lost its last frames
silently, and nothing looked. It is input-dependent rather than universal — the
template fixture loses three frames of 688, while the Cooper film's track is
long enough that both the old and the new renderer produce 24,119 — which is
precisely why it survived so long: it never showed up as a failure, only as a
film that was quietly a little shorter than the storyboard said. The same
defect was still live in the `--audio-only` remux, which advertises "frames
untouched" while overwriting the master in place; it now pads as well, and
refuses the swap outright if the frame count would change.

### 4. One worker per core made it *slower*

The obvious default — `-j 0` meaning `os.cpu_count()` — was measured and
rejected. On this 4+4-core, 8 GB machine, over the same 3,568 full-resolution
frames:

| workers | parallel phase | vs serial | kernel time |
|---|---|---|---|
| 1 | 379.0 s | 1.00× | 21.5 s |
| 2 | 220.5 s | 1.72× | 37.6 s |
| **4** | **154.5 s** | **2.45×** | 48.7 s |
| 8 | 317.8 s | 1.19× | 351.8 s |

Eight workers are **2.06× slower than four** and slower than two, and kernel
time grows seven-fold: the machine is paging, not rendering. Each worker holds
its own board, its own transform cache and its own encoder, so workers consume
memory instead of sharing it, and the four efficiency cores are roughly a third
the speed of the performance cores — they finish their segments long after the
rest.

`_default_jobs()` therefore bounds the count by the *performance* core count
(`hw.perflevel0.logicalcpu` on Apple Silicon, `/sys/devices/cpu_core/cpus` on
hybrid Linux) and by available memory, and reads cgroup limits directly because
neither `os.cpu_count()` nor `SC_PHYS_PAGES` can see a container's ceiling —
without that, a 2 GB CI container on a large host would start dozens of workers
and be OOM-killed. It resolves to 4 here, the measured optimum.

A worker that is killed outright — the OOM reaper, a segfault in a C library —
returns no result, and `multiprocessing.Pool` quietly replaces it without
re-queueing the segment it was holding. The result loop polls worker liveness
rather than blocking on a result that will never arrive, and fails with an
actionable message instead of hanging for ever.

### What it adds up to

The same film, the same machine, the same storyboard — 24,119 frames at
1920×1080, roughly thirteen and a half minutes of finished documentary.
"Before" is the committed pre-optimisation renderer run at *its* default,
which was `-j 1`; "after" is this one at its default, which resolves to 4 here.

| | wall clock | avg parallelism | kernel time |
|---|---|---|---|
| before | 6,475 s — **1 h 48 m** | 1.49× | 355 s |
| after | 1,527 s — **25.4 min** | 4.99× | 562 s |

**4.24×, or 82 minutes back on every render.** For scale, the intermediate
state is worth recording too: this same code with the naive "one worker per
core" default took 3,893 s (64.9 min) with 3,079 s of it in the kernel. Picking
the right worker count was worth 2.55× on its own — more than any single code
change here.

The remaining serial cost is the preamble — building the board and the audio
bed, about 106 s — which is a rounding error on a feature but dominates a short
fixture. The 23-second template spends most of its wall clock there, so it is a
good correctness fixture and a poor benchmark.

---

## GPU compositing: assessed and rejected

**The arithmetic that governs every option below.** Compose cost roughly
170 ms a frame before the current CPU-side fix; the fix is expected to bring
it to about 35 ms, which is the operative baseline from here on. Encoding
costs 165 ms a frame on a single thread — the thread count each segment's
encoder actually runs at, per the architecture above, not a hypothetical. A
GPU compositor that cut compose further, to a nominal 5 ms, would change the
per-frame total from 35 + 165 = 200 ms to 5 + 165 = 170 ms: 15% less time,
even though the compositor itself became seven times faster. That figure
assumes compose and encode run fully in series, which is the worst case for
a GPU's prospects; the best case is the fully overlapped one, where one
worker's Python side prepares the next frame while its ffmpeg child is still
draining the last, and encode alone — 165 ms either way — sets the pace, so
a faster compositor buys nothing measurable. The honest range for this
entire exercise, best case to worst case, is **0–15% off total render time**,
for whatever the library swap costs to build, debug and maintain, and
whatever share of the determinism guarantee it costs to spend. Every option
considered below sits inside that range, because none of them touches the
encoder, which is the actual bottleneck once the CPU-side fix lands.

**What freed cores are worth here.** The instinct that a faster compositor
"frees up cores" for something else does not transfer cleanly to this
codebase, because the resource that is short is not idle cores at all — it
is memory bandwidth and resident memory. `jobs` defaults to
`_default_jobs()`, which is deliberately **not** the core count: on the
reference machine it is 4 of 8, because each worker carries its own board,
its own transform cache and its own encoder, and running eight of them
measured *slower than running two* (318 s against 220 s, with kernel time up
seven-fold). Four cores therefore do sit idle by design — but they are idle
because the machine has run out of memory to feed them, not out of work, so
handing them a GPU-shaped job would not help either. Multithreading a single
x264 process to mop them up would cost more than it returns as well: at
roughly 48% parallel efficiency, a core spent there recovers less than half
of what the same core spent on another independent segment recovers.

**Apple Silicon's unified memory does not change this either.** The usual
counter-argument to GPU compositing in a CPU-bound pipeline is that the
composited frame has to travel back across a bus to reach the encoder, and
it is worth sizing precisely because it does not hold here. A raw 1920×1080
RGB24 frame is 1,920 × 1,080 × 3 = 6,220,800 bytes, about 6.2 MB — the same
figure this renderer's own segment worker already moves every frame today,
CPU to CPU, over an OS pipe (`_render_segment`'s own docstring in
`render.py` puts the earlier, now-replaced design's per-frame cost in
exactly those terms). Base Apple Silicon chips report roughly 68 GB/s of
unified memory bandwidth on the M1, rising to about 120 GB/s on the M4; at
those rates a single 6.2 MB transfer costs 52–91 microseconds, and a
composited frame would need at most a handful of such transfers — the
changed layers up, the finished frame back — before ffmpeg could see it.
Derate that by an order of magnitude for API and driver overhead on a
transfer this small and it is still comfortably under a millisecond, three
orders of magnitude below the 35–170 ms already budgeted for a frame. What
unified memory genuinely removes is the larger cost that would apply on a
discrete GPU — there is no PCIe bus to cross — so the "the frame has to come
back" objection, usually the strongest architectural argument against GPU
compositing in a pipeline like this one, is real but small here. It is
simply not the number that decides the question. Amdahl's law is.

**The precedent this project already sets.** `render.py` supports hardware
H.264 encoding behind an explicit `--hw` flag, and the reason is stated
plainly at the call site: hardware encoders are fixed-function silicon that
do not honour `-crf`, are not bit-exact between chip generations, and will
not produce agreeing output on two different machines, so — since
reproducibility is a documented property of this renderer — hardware
encoding can only ever be something the caller opts into by name. That is
the exact shape any GPU-compositing option below would have to take if it
were adopted at all: available, clearly named, never the default. The
question per option is not whether that compromise is workable — this
codebase already uses it elsewhere — but whether any option earns a place
behind such a flag at all, given the ceiling above.

With the shared arithmetic out of the way, here is what actually
differentiates the options: how mature the binding is, whether Apple Silicon
and Linux wheels both exist today, what the API hands you without writing a
shader, and whether it can promise the same bytes on a different machine.

| Option | Licence | Wheel today (macOS arm64, Python 3.14.6) | What it actually gives you |
|---|---|---|---|
| [skia-python](https://pypi.org/project/skia-python/) 144.0.post2 | BSD-3-Clause | Yes — prebuilt `cp314`/`cp314t` wheel | A CPU raster canvas by default; a GPU surface needs a context you build yourself |
| [moderngl](https://pypi.org/project/moderngl/) 5.12.0 | MIT | No prebuilt wheel yet; resolves via a source build | Raw OpenGL 4.1 plumbing — no resize, blur or composite call included |
| [pyobjc-framework-Metal](https://pypi.org/project/pyobjc-framework-Metal/) 12.2.2 | MIT | Yes, macOS only | A 1:1 Objective-C binding — you write the shaders |
| [wgpu](https://pypi.org/project/wgpu/) 0.32.0 | BSD-2-Clause | Yes — `py3-none`, Python-ABI-agnostic | Cross-platform WebGPU plumbing — no image ops included |
| [taichi](https://pypi.org/project/taichi/) 1.7.4 | Apache-2.0 | No — no wheel satisfies Python 3.14.6 today | A numerical-kernel DSL, not an image library |
| [cupy](https://pypi.org/project/cupy/) (cuda12x / cuda13x / rocm) | MIT | No — CUDA/ROCm only, no Apple Silicon path exists | Not applicable to this machine at all |
| [pyobjc-framework-Quartz](https://pypi.org/project/pyobjc-framework-Quartz/) 12.2.2 (Core Image) | MIT | Yes, macOS only | The closest API match: affine transform, Gaussian blur, a real Lanczos scale and compositing, all built in |
| [pyvips](https://pypi.org/project/pyvips/) + [pyvips-binary](https://pypi.org/project/pyvips-binary/) | MIT (binding) / LGPL-3.0-or-later (bundled libvips) | Yes — a single `cp37-abi3` wheel | A faster CPU rasteriser — not GPU compositing at all |

### skia-python

skia-python wraps Google's Skia, the rasteriser behind Chrome and Android,
and is genuinely well packaged: `144.0.post2` installs cleanly from a
prebuilt wheel on this exact machine — `cp314` and even the free-threaded
`cp314t` variant — plus wheels for Linux and Windows. Its version number
tracks Skia's own Chromium milestone counter rather than the binding's own
maturity, so 144 does not mean the Python layer is unusually battle-tested:
[HinTak and kyamagu maintain it](https://github.com/kyamagu/skia-python) as
a side project, not a company-backed SDK. The licence is unambiguous
(BSD-3-Clause, both the binding and upstream Skia), and the API genuinely
has what this renderer needs — `SkCanvas` composites over an arbitrarily
large surface, `skia.ImageFilters.Blur` is a real Gaussian blur, and affine
transforms are a matrix multiply away. Two things keep it from being a clean
win. The easy, zero-extra-dependency path through this binding is
`skia.Surface.MakeRaster`, a CPU rasteriser, not a GPU one, so adopting
skia-python for its API is a separate decision from adopting it for GPU
compositing: an actual `GrDirectContext` bound to Metal or OpenGL means
bringing a live graphics context from a separate windowing library first,
glue this renderer has no other use for. And even a from-scratch GPU build
would resample differently to Pillow — Skia's `SkSamplingOptions` offers a
cubic (Mitchell/Catmull-Rom) filter as its high-quality option, not a
Lanczos-windowed sinc, so the kernel changes, not only the engine. **Verdict:
the packaging and the CPU-side API are both good, but the only path to an
actual GPU surface reintroduces the determinism problem this document
exists to avoid, for a share of a ceiling already shown to be 0–15%.**

### moderngl

moderngl is a clean, well-regarded binding to OpenGL, MIT-licensed, carrying
a "Production/Stable" classifier on PyPI. Apple deprecated OpenGL across its
platforms at WWDC in June 2018, in favour of Metal, when macOS Mojave
shipped
([AppleInsider](https://appleinsider.com/articles/18/06/04/opengl-opencl-deprecated-in-favor-of-metal-2-in-macos-1014-mojave);
[Phoronix](https://www.phoronix.com/news/Apple-Deprecates-OpenGL-OpenCL)),
and the driver has been frozen at OpenGL 4.1 — a 2010-era specification,
with no compute shaders (which need 4.3+) and no route to get them, since
Apple does not allow third-party OpenGL drivers — ever since. That cap does
not actually block what this renderer needs: transform, blur and blend are
ordinary fragment-shader work that 4.1 handles without difficulty, so
"capped at 4.1" is a real, well-documented ceiling but not the load-bearing
objection for this use case. The load-bearing objection is that moderngl is
deliberately low-level — buffers, framebuffers and shader programs, with no
resize, blur or composite call anywhere in it — so every operation this
renderer currently gets for free from Pillow would need to be hand-written
as GLSL, a strictly larger undertaking than any higher-level option here, on
top of building on an API Apple has told developers to leave for seven
years. No prebuilt wheel exists yet for this machine's Python (3.14.6);
`pip` falls back to a source build, a minor but real addition to install
time on a fresh machine. **Verdict: capped, low-level, and built on an API
Apple wants gone — not worth writing a shader library for a ceiling this
small.**

### Metal via PyObjC

`pyobjc-framework-Metal` is a real, actively maintained part of the wider
pyobjc project — MIT-licensed, version 12.2.2, on the same release train as
`pyobjc-core` — and it does put genuine Metal access in front of Python.
What it does not do is give you anything resembling an image operation: it
is a 1:1 binding to Apple's Objective-C `Metal` framework, so using it means
allocating an `MTLDevice` and `MTLCommandQueue`, compiling Metal Shading
Language source at runtime, building a pipeline state, and managing command
buffers and encoders by hand for every one of transform, blur and composite
— there is no `resize()` or `gaussianBlur()` anywhere in `Metal` itself;
those live in Core Image or MetalPerformanceShaders, different frameworks.
A working version of what this renderer needs, built this way, is a few
hundred lines of new MSL and Python glue and, unlike any option above, a
wholly new subsystem with no counterpart anywhere else in this codebase to
model it on or share bugs with. It is also the one option in this whole
assessment that cannot run at all outside macOS, for a plugin whose only
stated requirements are `ffmpeg`, Python and two pip packages, installed by
users on whatever platform they run the CLI on. **Verdict: the most capable
low-level access on this list, and the least justified — hand-written
shaders for a gain already shown to be small, on one platform only.**

### wgpu-py

`wgpu` is the most comfortable of the low-level GPU bindings for this
renderer specifically, because it is the only one that is not macOS-only:
it wraps `wgpu-native`, the Rust WebGPU implementation Firefox itself uses,
targeting Metal on macOS and Vulkan or Direct3D 12 elsewhere, under a
BSD-2-Clause licence. Its wheels are also the most forward-looking here:
`py3-none` and platform-tagged rather than tied to a specific CPython ABI,
so — unlike skia-python, moderngl or taichi — it does not need a new
release every time Python does. Against all of that, the project is candid
about the one thing that matters most for a renderer that promises
reproducibility over years, not months: its own README states plainly that
"until WebGPU settles as a standard, its specification may change, and with
that our API will probably too"
([pygfx/wgpu-py](https://github.com/pygfx/wgpu-py)). A storyboard authored
today is meant to render identically in a year; a dependency whose own
maintainers expect its API to move before the underlying standard even
settles is a poor match for that promise, quite apart from needing the same
hand-written WGSL shaders for transform, blur and composite that moderngl
needs in GLSL. **Verdict: the best-packaged and most portable of the raw
graphics APIs, and still not worth it — low-level, and openly unstable by
its own account.**

### taichi

taichi is worth naming because it is a real, Apache-2.0-licensed project
with a genuine Metal backend alongside CUDA and Vulkan, and because it is
the clearest today-not-hypothetical blocker in this assessment: installing
it on this machine, Python 3.14.6, fails outright. The latest release,
1.7.4, ships wheels only up to `cp313`, with no source build to fall back
to, so `pip install taichi` reports that no version satisfies the
requirement at all. Even setting that aside, taichi is a numerical-kernel
DSL — `@ti.kernel` functions operating over `ti.field` tensors, aimed at
writing physics simulations and renderers from first principles — not an
image-compositing library; there is no resize, blur or alpha-over to call,
only the primitives to write one from scratch, a bigger undertaking than any
option that already exposes those operations directly. **Verdict: does not
install on the Python version this renderer already runs, and would still
mean writing an image library from scratch if it did.**

### CuPy

CuPy is "NumPy and SciPy for the GPU," and its own project page recommends
installing it by the name of the accelerator present —
[`cupy-cuda12x` or `cupy-cuda13x` for NVIDIA, `cupy-rocm-7-0` for AMD
ROCm](https://pypi.org/project/cupy/) — because there is no vendor-neutral
build. Apple Silicon has neither an NVIDIA nor an AMD GPU, so there is no
installable CuPy for this machine at all: this is a hardware-compatibility
question, not one of maturity, licensing or determinism. **Verdict: does
not run on the hardware this renderer targets — nothing further to
evaluate.**

### Core Image via PyObjC (Quartz)

Of every GPU-adjacent option here, Core Image — reached from Python through
`pyobjc-framework-Quartz` (MIT, version 12.2.2) — is the closest match to
what this renderer actually calls: `CIAffineTransform` for scale and rotate,
`CIGaussianBlur`, `CILanczosScaleTransform` (an actual Lanczos filter,
closer to Pillow's current kernel than Skia's cubic default), and ordinary
compositing filters, all present without writing a single shader. It is
also the option that comes closest to admitting, from the vendor itself,
the exact problem this document is about: a `CIContext` can render through
Metal, OpenGL or a CPU path, Apple's documentation does not claim identical
pixel output between them, and the context constructor exposes a
`useSoftwareRenderer` option whose sole purpose is to force the CPU path
([Apple Developer: `CIContext`](https://developer.apple.com/documentation/coreimage/cicontext)).
Apple never uses the word "deterministic" on that page, so this is an
inference rather than a documented guarantee — but the option would have no
reason to exist if the GPU and CPU paths were assured to agree. Using it to
get reproducible output forfeits the entire premise of adopting Core Image
for its GPU path, and even without that concession this is a macOS-only
framework, no more portable than Metal itself. **Verdict: the best API fit
of any option here, undercut by the vendor's own implicit determinism
caveat and its macOS-only reach.**

### pyvips — the CPU alternative, not a GPU one

pyvips is not GPU compositing, and it is included because the brief
specifically asked whether it should be considered anyway. libvips is a
real, mature C image library, independently benchmarked at several times
Pillow's speed for exactly the operations profiled above — the [project's
own wiki puts a representative resize-heavy workload at roughly 2.2× faster
than Pillow-SIMD](https://github.com/libvips/libvips/wiki/Speed-and-memory-use),
with plain Pillow slower again, and real-world reports commonly cite 5–10×
for large-image resize workloads. It also does something this renderer's
current code cannot: `Image.similarity(scale=, angle=)` resamples a
scale-and-rotate in a single pass, where `motion.transform()` (line 77)
resizes then rotates separately, so a port would improve fidelity as well as
speed. Packaging is the best of anything evaluated here — `pyvips[binary]`
resolves today to a single `cp37-abi3` wheel, meaning it keeps installing
unmodified on whatever CPython version this plugin's users run for years to
come, a promise none of the GPU-adjacent options can make. It is not free of
the determinism question, only smaller: swapping libraries is a one-time
break with previously rendered output regardless of which library is
chosen, and libvips' own release notes for its 8.15 line record that its
SIMD path has historically not matched the precision of its plain C path,
and that the newer dispatch mechanism still selects an implementation based
on the processor's own capabilities at runtime
([libvips.org, "What's new in libvips 8.15"](https://www.libvips.org/2023/10/10/What's-new-in-8.15.html))
— meaning the exact bytes produced can depend on which CPU rendered them, a
smaller, CPU-only version of the same risk that rules out the GPU options
above. The licence is worth flagging on its own terms too: the binding
itself is MIT, matching the rest of this project, but the bundled binary
distribution most people actually install, `pyvips-binary`, carries
libvips' own LGPL-3.0-or-later — a copyleft term with no equivalent
elsewhere in this plugin's dependencies. None of that changes the
arithmetic above: pyvips would optimise a stage that, once the CPU-side
memoisation fix lands, is already the cheaper half of the frame budget, so a
full port is unlikely to move total render time by anything that justifies
rewriting every call site that currently talks to Pillow directly. **Verdict:
real, cheap to trial on the hot path alone, and worth keeping in reserve —
but not a fix for anything this profile currently blames on the
compositor.**

---

## If you ever revisit this

The verdicts above hold for the pipeline as measured here, not forever, and
four concrete changes would be reason to redo this analysis rather than
trust it by default.

If the encoder stops being fixed at roughly 165 ms a frame — most plausibly
by moving to a hardware encoder such as ffmpeg's `h264_videotoolbox`, which
`render.py` already supports behind the `--hw` flag described above,
precisely because hardware encoders are not bit-exact between chip
generations and have to stay opt-in — compose becomes the dominant cost
again and this comparison should be rerun with the new number. Start that
rerun with pyvips, not a GPU: it is cheaper to trial, and it is already
faster than Pillow on every operation this renderer needs.

If skia-python, or any option above, ships a raster path verified
byte-identical, for a pinned version, across every platform this plugin is
actually distributed on — macOS arm64 and x86_64, Linux x86_64 and aarch64,
Windows — rather than that being an assumption nobody has tested, the
CPU-library objection weakens specifically for that library. The Amdahl
ceiling computed above would still need to have moved before the rewrite
was worth it.

If the render pipeline stops handing ffmpeg raw frames over a CPU-side pipe
— for instance, by driving VideoToolbox directly from a GPU-resident
texture — the upload/readback cost this document puts at under a
millisecond stops being negligible only because it stops existing at all.
That is an argument for moving compositing and encoding to the GPU
together, not for moving compositing there alone while encoding stays on
the CPU exactly as it is today.

If a future storyboard needs a visual effect Pillow genuinely cannot
produce at all — real-time depth of field across dozens of stacked layers,
or a particle system with thousands of independent instances — that is a
different question from whether the current renderer is fast enough, and
should be judged on whether the effect is achievable, not folded into a
cost-per-frame argument built for a renderer that already does everything it
needs to on the CPU.
