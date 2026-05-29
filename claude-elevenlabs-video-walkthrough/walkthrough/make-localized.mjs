/**
 * Generates localized manifests (steps.<lang>.json) from the base English
 * steps.json. Each variant reuses the same English screenshots (shots/) but
 * points its audio + overlays at a per-language subdir, so the downstream
 * narrate / overlays / render stages can build a separate video per language:
 *
 *   MANIFEST=steps.fr.json npm run narrate
 *   MANIFEST=steps.fr.json npm run overlays
 *   MANIFEST=steps.fr.json CLIPS_DIR=fr/clips OUTPUT=walkthrough-fr.mp4 npm run render
 *
 * The voice (George) and model (eleven_multilingual_v2) are unchanged — the
 * multilingual model speaks each language from the translated text below.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const BASE = join(ROOT, 'steps.json');

// Per-language: header strings, UI labels, and {caption, narration} keyed by
// the step `name` from the base manifest.
const LANGS = {
  fr: {
    title: 'Acme — Contacter un humain',
    purpose: 'Capture Claude + Playwright · narration ElevenLabs (George) · assemblage ffmpeg',
    flag: 'fr',
    labels: { walkthrough: 'Démonstration', step: 'Étape', of: 'sur' },
    steps: {
      home: {
        caption: "Page d'accueil",
        narration:
          "Bienvenue sur Acme — notre produit de démonstration volontairement banal. Un visiteur arrive sur la page d'accueil, et l'appel à l'action principal est bien en évidence : Nous contacter.",
      },
      'contact-open': {
        caption: 'Formulaire de contact ouvert',
        narration:
          "En cliquant sur Nous contacter, le visiteur est dirigé vers un simple formulaire de contact. Trois champs — nom, e-mail et message — et un seul bouton d'envoi. Rien de compliqué.",
      },
      validation: {
        caption: 'Validation en ligne',
        narration:
          "Soumettre un formulaire vide fait apparaître une validation en ligne sur chaque champ. Aucune donnée incorrecte n'atteint le serveur — l'utilisateur voit exactement ce qui manque.",
      },
      filled: {
        caption: 'Formulaire complété',
        narration:
          "Une fois les champs remplis avec des données valides, les erreurs en ligne disparaissent automatiquement et le formulaire est prêt à être envoyé.",
      },
      'ready-to-send': {
        caption: 'Prêt à envoyer',
        narration:
          "Tous les champs étant valides, le bouton Envoyer le message est désormais actif. Un seul clic envoie le message au serveur.",
      },
      success: {
        caption: 'Envoi confirmé',
        narration:
          "La requête POST vers /api/contact aboutit, et l'utilisateur arrive sur une page de confirmation comportant un identifiant de ticket unique.",
      },
      admin: {
        caption: 'Apparaît dans les soumissions',
        narration:
          "Et voici la preuve de bout en bout. La soumission apparaît dans la liste du back-office avec un horodatage récent — exactement la ligne qu'Ada vient de créer.",
      },
    },
  },

  es: {
    title: 'Acme — Contactar con una persona',
    purpose: 'Captura con Claude + Playwright · narración de ElevenLabs (George) · montaje con ffmpeg',
    flag: 'es',
    labels: { walkthrough: 'Recorrido', step: 'Paso', of: 'de' },
    steps: {
      home: {
        caption: 'Página de inicio',
        narration:
          'Bienvenido a Acme — nuestro producto de demostración deliberadamente aburrido. Un visitante llega a la página de inicio y la llamada a la acción principal está bien visible: Ponte en contacto.',
      },
      'contact-open': {
        caption: 'Formulario de contacto abierto',
        narration:
          'Al hacer clic en Ponte en contacto, el visitante llega a un sencillo formulario de contacto. Tres campos — nombre, correo electrónico y mensaje — y un único botón de envío. Nada complicado.',
      },
      validation: {
        caption: 'Validación en línea',
        narration:
          'Al enviar un formulario vacío aparece la validación en línea en cada campo. Ningún dato incorrecto llega al servidor — el usuario ve exactamente qué falta.',
      },
      filled: {
        caption: 'Formulario completado',
        narration:
          'Una vez que los campos se rellenan con datos válidos, los errores en línea desaparecen automáticamente y el formulario está listo para enviarse.',
      },
      'ready-to-send': {
        caption: 'Listo para enviar',
        narration:
          'Con todos los campos válidos, el botón Enviar mensaje ya está activo. Un solo clic envía el mensaje al servidor.',
      },
      success: {
        caption: 'Envío confirmado',
        narration:
          'La solicitud POST a /api/contact se completa con éxito y el usuario llega a una página de confirmación con un identificador de ticket único.',
      },
      admin: {
        caption: 'Aparece en los envíos',
        narration:
          'Y aquí está la prueba de principio a fin. El envío aparece en la lista del back office con una marca de tiempo reciente — exactamente la fila que Ada acaba de crear.',
      },
    },
  },

  ja: {
    title: 'Acme — 人間に問い合わせる',
    purpose: 'Claude + Playwright でキャプチャ · ElevenLabs（George）がナレーション · ffmpeg で結合',
    flag: 'ja',
    labels: { walkthrough: 'ウォークスルー', step: 'ステップ', of: '/' },
    steps: {
      home: {
        caption: 'ランディングページ',
        narration:
          'Acme へようこそ。あえて地味に作ったデモ用の製品です。訪問者がホームページに到着すると、主要な行動喚起がすぐ目の前にあります。「お問い合わせ」です。',
      },
      'contact-open': {
        caption: '問い合わせフォームを表示',
        narration:
          '「お問い合わせ」をクリックすると、訪問者はシンプルな問い合わせフォームに移動します。名前、メールアドレス、メッセージという三つの入力欄と、送信ボタンが一つだけ。凝った仕組みはありません。',
      },
      validation: {
        caption: 'インラインバリデーション',
        narration:
          '空のフォームを送信すると、各入力欄にインラインのバリデーションが表示されます。不正なデータがバックエンドに届くことはなく、利用者には何が足りないかが正確に示されます。',
      },
      filled: {
        caption: 'フォーム入力完了',
        narration:
          '各入力欄に正しい内容を入力すると、インラインのエラーは自動的に消え、フォームは送信できる状態になります。',
      },
      'ready-to-send': {
        caption: '送信の準備完了',
        narration:
          'すべての入力欄が有効になり、「メッセージを送信」ボタンが有効化されました。クリックひとつでメッセージがバックエンドに送信されます。',
      },
      success: {
        caption: '送信完了',
        narration:
          '/api/contact への POST リクエストが成功し、利用者は固有のチケット番号が表示された確認ページに移動します。',
      },
      admin: {
        caption: '送信一覧に表示',
        narration:
          'そしてこれがエンドツーエンドの証拠です。送信内容が新しいタイムスタンプとともにバックオフィスの一覧に表示されます。まさに Ada がいま作成した行です。',
      },
    },
  },
};

async function main() {
  const base = JSON.parse(await readFile(BASE, 'utf8'));

  for (const [lang, tr] of Object.entries(LANGS)) {
    const steps = base.steps.map((s) => {
      const t = tr.steps[s.name];
      if (!t) throw new Error(`Missing ${lang} translation for step "${s.name}"`);
      const pad = String(s.n).padStart(2, '0');
      return {
        ...s,
        caption: t.caption,
        narration: t.narration,
        // shots stay shared (English UI); audio + overlays go to a lang subdir
        audio: `${lang}/audio/${pad}-${s.name}.mp3`,
        titleOverlay: `${lang}/overlays/${pad}-title.png`,
        captionOverlay: `${lang}/overlays/${pad}-caption.png`,
      };
    });

    const manifest = {
      title: tr.title,
      purpose: tr.purpose,
      lang,
      flag: tr.flag,
      labels: tr.labels,
      viewport: base.viewport,
      voice: base.voice,
      steps,
    };

    const out = join(ROOT, `steps.${lang}.json`);
    await writeFile(out, JSON.stringify(manifest, null, 2));
    console.log(`✓ ${lang} → ${out}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
