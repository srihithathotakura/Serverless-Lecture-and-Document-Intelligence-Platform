import { api } from './api.js';

const fmt = (s) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export async function showDetail(box, documentId, onBack) {
  box.replaceChildren('Loading…');

  try {
    const { document: d, textUrl } = await api(
      '/documents/' + documentId,
    );

    box.replaceChildren();

    const h = document.createElement('h2');
    h.textContent = d.fileName;
    box.append(h);

    const s = document.createElement('p');
    s.textContent = 'Status: ' + d.status;
    box.append(s);

    if (d.status === 'FAILED') {
      const e = document.createElement('p');
      e.className = 'error';
      e.textContent = d.errorMessage || 'Processing failed.';
      box.append(e);
    }

    if (d.summary) {
      const t = document.createElement('h3');
      t.textContent = 'Summary';

      const p = document.createElement('p');
      p.textContent = d.summary;
      box.append(t, p);
    }

    if (textUrl) {
      const t = document.createElement('h3');
      t.textContent = d.fileType === 'audio' ? 'Transcript' : 'Text';
      box.append(t);

      // Presigned URL: do not send the Cognito Authorization header.
      const res = await fetch(textUrl);

      if (!res.ok) {
        throw new Error('Unable to load document text.');
      }

      const { segments } = await res.json();

      for (const seg of segments) {
        const p = document.createElement('p');
        const label = seg.page
          ? `Page ${seg.page}`
          : `${fmt(seg.startSec)}–${fmt(seg.endSec)}`;

        p.textContent = `[${label}] ${seg.text}`;
        box.append(p);
      }
    }

    const del = document.createElement('button');
    del.textContent = 'Delete';

    del.onclick = async () => {
      if (!confirm(`Delete "${d.fileName}"? This cannot be undone.`)) {
        return;
      }

      try {
        await api('/documents/' + documentId, { method: 'DELETE' });
        onBack();
      } catch (e) {
        alert(e.message);
      }
    };

    const back = document.createElement('button');
    back.textContent = 'Back';
    back.onclick = onBack;

    box.append(back, del);
  } catch (e) {
    box.textContent = e.message;
  }
}
