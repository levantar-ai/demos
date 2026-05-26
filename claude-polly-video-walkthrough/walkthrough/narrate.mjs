/**
 * Stage 2 of the video pipeline.
 *
 * Reads presentation/steps.json and, for each step, asks AWS Polly to
 * synthesize the narration with the voice declared at the top of the
 * manifest (Arthur, en-GB, neural engine). Writes one MP3 per step.
 *
 * Run as:
 *   aws-vault exec personal_iphone -- npm run narrate
 *
 * The script is intentionally stateless — re-running just overwrites
 * the audio files, which is what you want after editing narration text.
 */
import { PollyClient, SynthesizeSpeechCommand } from '@aws-sdk/client-polly';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const MANIFEST = join(ROOT, 'steps.json');
const AUDIO_DIR = join(ROOT, 'audio');

async function main() {
  const manifest = JSON.parse(await readFile(MANIFEST, 'utf8'));
  const { voice, steps } = manifest;
  if (!voice?.id) throw new Error('Manifest is missing voice config — run `npm run capture` first.');

  await mkdir(AUDIO_DIR, { recursive: true });

  const polly = new PollyClient({ region: process.env.AWS_REGION || 'eu-west-2' });

  for (const step of steps) {
    process.stdout.write(`  step ${step.n}: synthesizing ${step.audio} … `);

    const out = await polly.send(
      new SynthesizeSpeechCommand({
        Text: step.narration,
        TextType: 'text',
        VoiceId: voice.id,
        Engine: voice.engine || 'neural',
        LanguageCode: voice.languageCode || 'en-GB',
        OutputFormat: 'mp3',
        SampleRate: '24000',
      }),
    );

    const path = join(ROOT, step.audio);
    const bytes = await streamToBuffer(out.AudioStream);
    await writeFile(path, bytes);
    console.log(`${bytes.length.toLocaleString()} bytes`);
  }

  console.log(`\n✓ ${steps.length} clips → ${AUDIO_DIR}`);
}

async function streamToBuffer(stream) {
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return Buffer.concat(chunks);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
