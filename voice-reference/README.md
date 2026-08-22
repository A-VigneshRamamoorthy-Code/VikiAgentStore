# Voice reference

Reference AI voice samples, kept for voiceover / TTS cloning work (e.g. the
`faceless-video` and `product-launch` skills).

All samples are mono.

## English (omnivoice)

16-bit PCM WAV.

| File | Source | Rate | Duration |
|------|--------|------|----------|
| `female-american.wav` | <https://cysource.omnivoice.app/voice/ALLE.wav> | 24 kHz | 10.76 s |
| `female-british.wav` | <https://cysource.omnivoice.app/voice/bbcnews-female.wav> | 16 kHz | 6.47 s |
| `male-american.wav` | <https://cysource.omnivoice.app/voice/American%20audio-male.wav> | 16 kHz | 8.07 s |
| `male-energetic.wav` | <https://cysource.omnivoice.app/voice/Energetic%20Male.wav> | 24 kHz | 10.68 s |

## Tamil (ElevenLabs)

MP3, 128 kbps.

| File | Rate | Duration |
|------|------|----------|
| `tamil-male.mp3` | 44.1 kHz | 7.65 s |
| `tamil-female.mp3` | 44.1 kHz | 9.38 s |
| `tamil-female-2.mp3` | 44.1 kHz | 5.33 s |

Files are renamed from their source names to describe the voice, and kept
kebab-case so they are safe to pass to shell tooling without quoting.

## Re-downloading

```bash
cd voice-reference

# English (omnivoice)
curl -sSL -o female-american.wav "https://cysource.omnivoice.app/voice/ALLE.wav"
curl -sSL -o female-british.wav  "https://cysource.omnivoice.app/voice/bbcnews-female.wav"
curl -sSL -o male-american.wav   "https://cysource.omnivoice.app/voice/American%20audio-male.wav"
curl -sSL -o male-energetic.wav  "https://cysource.omnivoice.app/voice/Energetic%20Male.wav"

# Tamil (ElevenLabs)
ELEVEN=https://storage.googleapis.com/eleven-public-prod/database/workspace/ed9b05e6324c457685490352e9a1ec90/voices
curl -sSL -o tamil-male.mp3     "$ELEVEN/gJvkwI7wGFW2czmyfJhp/JgCM4B5PjDYK8E2vgAn1.mp3"
curl -sSL -o tamil-female.mp3   "$ELEVEN/IC6fkbI5BN65xFmhUCbY/UKI8e2n6BWpmFpumeCHF.mp3"
curl -sSL -o tamil-female-2.mp3 "$ELEVEN/u7DoEF74Zzu8FP2dxDfk/JuIpU4DkRzJDib5rxAMq.mp3"
```
