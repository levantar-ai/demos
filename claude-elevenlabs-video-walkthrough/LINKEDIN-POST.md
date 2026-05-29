# LinkedIn post — ElevenLabs voice + Claude translation (localized walkthrough)

Follow-on to the Polly narrated-video post. Focus: ElevenLabs for the voice,
Claude for the translation. No em dashes (per preference).

Demo page (live): https://levantar-ai.github.io/demos/claude-elevenlabs-video-walkthrough/

---

Four languages. Fifteen minutes. One demo. 🌍

ElevenLabs handled the voice, Claude handled the translation, and I didn't record, translate, or re-edit a single word myself. I wrote the narration once, in English.

In the previous post I shared a pipeline where Claude drives Playwright through a live app and stitches the result into a narrated MP4. I flagged two gaps at the end: the AWS Polly voice was generic-pleasant rather than human, and localization was still on the to-do list. This post closes both, and the pipeline barely changed to do it.

**ElevenLabs for the voice.** I swapped Polly for ElevenLabs (https://elevenlabs.io/). Same narration text, same capture, same ffmpeg stitch. Only one stage of the pipeline changed. But the voice (a British narrator called "George") lands much closer to a real person, which makes a real difference for anything a customer watches rather than just an internal demo loop. 🎧

**Claude for the translation.** I had Claude translate every step, including the spoken narration, the on-screen captions, and the UI labels, into French, Spanish and Japanese. No translation vendor, no per-locale recording session, no second take. ElevenLabs' multilingual model then voices all of them in that same "George" voice, so it sounds consistent across languages. One source script in, three additional fully-narrated videos out.

One honest bit of scoping. I localized the narration layer, not the app chrome. The app's own buttons stay in English on purpose, because the point was to show the storytelling layer translating end to end, voice and captions together, without anyone touching the underlying app.

That same "post-process without touching the app" principle from last time still holds. Each video's title bar now carries the language's flag, dropped into the spare space entirely in the ffmpeg overlay stage. Restyle it, reword it, or regenerate a single language without re-running capture. ⚙️

And the single-source-of-truth rule survives translation: one step array still declares the Playwright actions, the highlight, the caption, and the narration, now per locale. Visuals, audio, and story can't drift apart, in any language.

Cost and time? A handful of pennies of ElevenLabs characters and about fifteen minutes on a laptop for all four languages.

The demo is live here: https://levantar-ai.github.io/demos/claude-elevenlabs-video-walkthrough/

If your docs only exist in English today, what's the real blocker to shipping them in five more: the translation, the voice talent, or the production time? 🤔
