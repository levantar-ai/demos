/**
 * Post-process stage 2 of 2.
 *
 * For each step:
 *   - read the matching MP3 to learn its exact duration (ffprobe);
 *   - composite the captured still + the title-bar PNG (top) + the
 *     caption-bar PNG (bottom) into a video clip whose audio track is
 *     the narration MP3 with a short silent head/tail pad.
 *
 * Then concat all clips losslessly into presentation/walkthrough.mp4.
 *
 * Requires ffmpeg + ffprobe on $PATH.
 */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const exec = promisify(execFile);

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const CLIPS = join(ROOT, 'clips');
const OUTPUT = join(ROOT, 'walkthrough.mp4');

const TAIL_PAD_SECONDS = 0.6;
const HEAD_PAD_SECONDS = 0.3;
const TOP_MARGIN = 24;     // px from top of frame to title bar
const BOTTOM_MARGIN = 24;  // px from bottom of frame to caption bar

async function probeDuration(path) {
  const { stdout } = await exec('ffprobe', [
    '-v', 'error',
    '-show_entries', 'format=duration',
    '-of', 'default=noprint_wrappers=1:nokey=1',
    path,
  ]);
  return parseFloat(stdout.trim());
}

async function renderClip(step) {
  const stillPath = join(ROOT, 'shots', step.file);
  const audioPath = join(ROOT, step.audio);
  const titlePath = join(ROOT, step.titleOverlay);
  const captionPath = join(ROOT, step.captionOverlay);
  const clipPath = join(CLIPS, `${String(step.n).padStart(2, '0')}-${step.name}.mp4`);

  const narrationSeconds = await probeDuration(audioPath);
  const total = (HEAD_PAD_SECONDS + narrationSeconds + TAIL_PAD_SECONDS).toFixed(3);

  // Inputs:
  //   0 = still PNG (looped)
  //   1 = title bar PNG (looped)
  //   2 = caption bar PNG (looped)
  //   3 = silence (head pad)
  //   4 = narration MP3
  //   5 = silence (tail pad)
  //
  // Filter graph:
  //   [base]    = scaled/padded still to 1920x1080, 30fps
  //   [withT]   = overlay title bar centered horizontally, TOP_MARGIN from top
  //   [withTC]  = overlay caption bar centered horizontally, BOTTOM_MARGIN from bottom
  //   [a]       = silence + narration + silence concatenated
  const args = [
    '-y',
    '-loop', '1', '-framerate', '30', '-i', stillPath,
    '-loop', '1', '-framerate', '30', '-i', titlePath,
    '-loop', '1', '-framerate', '30', '-i', captionPath,
    '-f', 'lavfi', '-t', String(HEAD_PAD_SECONDS), '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
    '-i', audioPath,
    '-f', 'lavfi', '-t', String(TAIL_PAD_SECONDS), '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
    '-filter_complex',
      // The overlay PNGs are rendered at 2x for crisp text (3000px wide);
      // scale them down to 1500px before compositing so they sit centered
      // inside the 1920px frame with sensible side margins.
      `[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,` +
      `pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0b1120,setsar=1,fps=30[base];` +
      `[1:v]scale=1500:-1[title];` +
      `[2:v]scale=1500:-1[caption];` +
      `[base][title]overlay=x=(W-w)/2:y=${TOP_MARGIN}[withT];` +
      `[withT][caption]overlay=x=(W-w)/2:y=H-h-${BOTTOM_MARGIN}[v];` +
      `[3:a][4:a][5:a]concat=n=3:v=0:a=1[a]`,
    '-map', '[v]', '-map', '[a]',
    '-t', total,
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'medium', '-crf', '20',
    '-c:a', 'aac', '-b:a', '160k',
    '-shortest',
    clipPath,
  ];

  process.stdout.write(`  step ${step.n}: ${step.name} → ${(parseFloat(total)).toFixed(1)}s clip … `);
  await exec('ffmpeg', args);
  console.log('done');
  return clipPath;
}

async function concatClips(clipPaths) {
  const listPath = join(CLIPS, 'concat.txt');
  await writeFile(listPath, clipPaths.map((p) => `file '${p}'`).join('\n') + '\n');

  const args = [
    '-y',
    '-f', 'concat', '-safe', '0', '-i', listPath,
    '-c', 'copy',
    OUTPUT,
  ];
  console.log(`\n  concat → ${OUTPUT}`);
  await exec('ffmpeg', args);
}

async function main() {
  const manifest = JSON.parse(await readFile(join(ROOT, 'steps.json'), 'utf8'));
  await rm(CLIPS, { recursive: true, force: true });
  await mkdir(CLIPS, { recursive: true });

  const paths = [];
  for (const step of manifest.steps) {
    paths.push(await renderClip(step));
  }
  await concatClips(paths);

  const finalSeconds = await probeDuration(OUTPUT);
  console.log(`\n✓ walkthrough.mp4 — ${finalSeconds.toFixed(1)}s, ${manifest.steps.length} steps`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
