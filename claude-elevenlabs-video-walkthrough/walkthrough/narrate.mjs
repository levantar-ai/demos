/**
 * Stage 2 of the video pipeline.
 *
 * Reads presentation/steps.json and, for each step, asks ElevenLabs to
 * synthesize the narration with the voice declared at the top of the
 * manifest (George, a warm British storyteller voice). Writes one MP3
 * per step.
 *
 * Run as:
 *   ELEVENLABS_API_KEY=sk_... npm run narrate
 *
 * The script is intentionally stateless — re-running just overwrites
 * the audio files, which is what you want after editing narration text.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
// MANIFEST may be overridden to build a localized variant (e.g. steps.fr.json).
// Audio output paths are taken from each step, so per-language manifests just
// point step.audio at their own subdir.
const MANIFEST = process.env.MANIFEST
  ? (process.env.MANIFEST.startsWith('/') ? process.env.MANIFEST : join(ROOT, process.env.MANIFEST))
  : join(ROOT, 'steps.json');

const API_KEY = process.env.ELEVENLABS_API_KEY;

async function main() {
  if (!API_KEY) {
    throw new Error('Set ELEVENLABS_API_KEY in the environment before running narrate.');
  }

  const manifest = JSON.parse(await readFile(MANIFEST, 'utf8'));
  const { voice, steps } = manifest;
  if (!voice?.id) throw new Error('Manifest is missing voice config — run `npm run capture` first.');

  const modelId = voice.modelId || 'eleven_multilingual_v2';

  for (const step of steps) {
    process.stdout.write(`  step ${step.n}: synthesizing ${step.audio} … `);

    const res = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${voice.id}?output_format=mp3_44100_128`,
      {
        method: 'POST',
        headers: {
          'xi-api-key': API_KEY,
          'Content-Type': 'application/json',
          Accept: 'audio/mpeg',
        },
        body: JSON.stringify({
          text: step.narration,
          model_id: modelId,
          voice_settings: {
            stability: 0.5,
            similarity_boost: 0.75,
            style: 0.0,
            use_speaker_boost: true,
          },
        }),
      },
    );

    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error(`ElevenLabs returned ${res.status} ${res.statusText}: ${detail}`);
    }

    const bytes = Buffer.from(await res.arrayBuffer());
    const path = join(ROOT, step.audio);
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, bytes);
    console.log(`${bytes.length.toLocaleString()} bytes`);
  }

  console.log(`\n✓ ${steps.length} clips → ${dirname(join(ROOT, steps[0].audio))}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
