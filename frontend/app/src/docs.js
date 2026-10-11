import { api } from './api.js';

const STEP_LABELS = {
  TRANSCRIBING: 'Transcribing audio',
  EXTRACTING: 'Reading PDF text',
  CHUNKING: 'Splitting text',
  SUMMARIZING: 'Writing summary',
  INDEXING: 'Building search index',
};

const ACTIVE = ['UPLOADING', 'PROCESSING'];
let timer = null;

export function stopPolling() {
  clearTimeout(timer);
  timer = null;
}

export async function refreshList(tbody, errorEl, onOpen) {
  stopPolling();

  try {
    const { documents } = await api('/documents');
    errorEl.textContent = '';
    render(tbody, documents, onOpen);

    if (documents.some((d) => ACTIVE.includes(d.status))) {
      timer = setTimeout(() => refreshList(tbody, errorEl, onOpen), 5000);
    }
  } catch (e) {
    errorEl.textContent = e.message + ' (click Refresh to retry)';
  }
}

function render(tbody, docs, onOpen) {
  tbody.replaceChildren();

  if (!docs.length) {
    const tr = tbody.insertRow();
    const td = tr.insertCell();
    td.colSpan = 5;
    td.textContent = 'No documents yet. Upload a WAV or PDF above.';
    return;
  }

  for (const d of docs) {
    const tr = tbody.insertRow();

    const name = tr.insertCell();
    name.textContent = d.fileName;
    name.style.cursor = 'pointer';
    name.onclick = () => onOpen(d.documentId);

    tr.insertCell().textContent =
      d.fileType === 'audio' ? 'Audio' : 'PDF';

    const st = tr.insertCell();
    st.textContent = d.status;
    st.className = 'badge ' + d.status.toLowerCase();

    tr.insertCell().textContent =
      d.status === 'PROCESSING'
        ? STEP_LABELS[d.step] || 'Working…'
        : '';

    tr.insertCell().textContent =
      new Date(d.createdAt).toLocaleString();
  }
}
