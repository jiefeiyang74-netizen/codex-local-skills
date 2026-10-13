# Optional native final encoder

The default remains Manim's software writer. Set request field
`final_encoder_profile: "nvenc_p5_cq22_rgba_60_v1"` only for an explicitly requested GPU final.
Preview still uses software. Unknown profiles fail; encoder failure never silently falls back.

This fixed opaque MP4/Cairo/60fps profile feeds native RGBA frames to the runtime-configured,
absolute FFmpeg executable: `h264_nvenc -preset p5 -rc vbr -cq 22 -b:v 0 -pix_fmt yuv420p`.
Both movie and video timescales are 60000. Each partial must have every PTS exactly i/60,
N frames and duration N/60; if necessary, a lossless container remux repairs its timing.
Manim's existing PyAV partial concatenation remains in charge of the single scene output.
Neither audio nor scene actions/clocks are changed. No GPU dependency is installed.

`manifest.encoder` records the fixed contract, executable SHA256 and writer SHA256.
`manifest.encoding_identity` combines that contract with the content `identity` for output reuse;
the visual review gate continues to bind content identity. Separate attempt-local partials are retained.
Executable paths belong to runtime/generated local code, never to this portable profile.

The writer is a scene-local `NativeGeometrySceneFileWriter` subclass. The native camera is created
after canvas aspect is configured. The global software writer is untouched.
