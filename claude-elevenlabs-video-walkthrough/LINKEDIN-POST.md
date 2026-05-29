# LinkedIn post — ElevenLabs voice + Claude translation (localized walkthrough)

Follow-on to the Polly narrated-video post. Focus: ElevenLabs for the voice,
Claude for the translation. No em dashes (per preference).

Demo page (live): https://levantar-ai.github.io/demos/claude-elevenlabs-video-walkthrough/

---

Four languages. Fifteen minutes. One demo. 🌍

ElevenLabs handled the voice, Claude handled the translation, and I didn't record, translate, or re-edit a single word myself. I wrote the narration once, in English.

This builds on the pipeline from my last post, where Claude drives Playwright through a live app and ffmpeg stitches the captured steps into a narrated MP4. Last time I flagged two gaps, a human-sounding voice and localization. This closes both, and the pipeline barely changed.

**ElevenLabs for the voice.** I swapped Polly for ElevenLabs (https://elevenlabs.io/). Same narration text, same capture, same ffmpeg stitch, only one stage changed. The voice (a British narrator called "George") lands much closer to a real person, which matters for anything a customer watches rather than just an internal demo loop. 🎧

**Claude for the translation.** I had Claude translate every step, including the spoken narration, the on-screen captions, and the UI labels, into French, Spanish and Japanese. No translation vendor, no per-locale recording session, no second take. ElevenLabs' multilingual model then voices all of them in that same "George" voice, so it sounds consistent across languages. One source script in, three additional fully-narrated videos out.

I localized the narration layer, not the app chrome. The app's own buttons stay in English on purpose, because the point was to show the storytelling layer translating end to end, voice and captions together, without anyone touching the underlying app.

This is AI translation, and I don't speak French, Spanish or Japanese, so I can't verify the output myself. For anything customer-facing you'd want a native speaker to review it before shipping.

The flags sit in each title bar, composited in post by ffmpeg without touching the app, so I can restyle or regenerate a single language without re-capturing. And one step array still drives the Playwright actions, the highlight, the caption and the narration per locale, so visuals, audio and story stay in sync. ⚙️

Cost? Nothing. It fit inside ElevenLabs' free tier (10,000 credits a month, plenty for a demo), and the translation just used my existing Claude subscription. About fifteen minutes on a laptop for all four languages.

The demo is live here: https://levantar-ai.github.io/demos/claude-elevenlabs-video-walkthrough/

If you have an international customer base, this is a cheap way to meet people in their own language without a studio or a translation agency. And if that's you, what's held the localized version back so far: the translation, the voice talent, or the production time? 🤔
