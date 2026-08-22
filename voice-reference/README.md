# Voice reference

Reference AI voice samples, kept for voiceover / TTS cloning work (e.g. the
`faceless-video` and `product-launch` skills).

All files are 16-bit mono PCM WAV.

| File | Source | Rate | Duration |
|------|--------|------|----------|
| `alle.wav` | <https://cysource.omnivoice.app/voice/ALLE.wav> | 24 kHz | 10.76 s |
| `bbcnews-female.wav` | <https://cysource.omnivoice.app/voice/bbcnews-female.wav> | 16 kHz | 6.47 s |
| `american-audio-male.wav` | <https://cysource.omnivoice.app/voice/American%20audio-male.wav> | 16 kHz | 8.07 s |
| `energetic-male.wav` | <https://cysource.omnivoice.app/voice/Energetic%20Male.wav> | 24 kHz | 10.68 s |

Filenames are kebab-cased from the source names so they are safe to pass to
shell tooling without quoting.

## Re-downloading

```bash
cd voice-reference
curl -sSL -o alle.wav                 "https://cysource.omnivoice.app/voice/ALLE.wav"
curl -sSL -o bbcnews-female.wav       "https://cysource.omnivoice.app/voice/bbcnews-female.wav"
curl -sSL -o american-audio-male.wav  "https://cysource.omnivoice.app/voice/American%20audio-male.wav"
curl -sSL -o energetic-male.wav       "https://cysource.omnivoice.app/voice/Energetic%20Male.wav"
```
