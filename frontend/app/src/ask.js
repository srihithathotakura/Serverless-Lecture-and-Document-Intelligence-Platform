import { api } from './api.js';

export async function ask(question, documentId) {
  const body = { question };
  if (documentId) body.documentId = documentId;

  return api('/ask', {
    method: 'POST',
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(35000),
  });
}

export function renderAnswer(box, res) {
  box.replaceChildren();

  const citations = Array.isArray(res.citations) ? res.citations : [];

  if (citations.length === 0) {
    const message = document.createElement('p');
    message.className = 'notfound';
    message.textContent =
      'I could not find this in your documents. Try words that appear in the document. Search is keyword-based.';
    box.append(message);
    return;
  }

  const busy = /busy|try again/i.test(res.answer || '');
  const answer = document.createElement('p');
  answer.className = busy ? 'notice' : 'answer';
  answer.textContent = busy
    ? 'The answer service is busy right now. Here are the best matching passages from your documents:'
    : (res.answer || 'Best matching passages:');
  box.append(answer);

  const heading = document.createElement('h4');
  heading.textContent = 'Sources';
  box.append(heading);

  const list = document.createElement('ul');

  for (const citation of citations) {
    const item = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = `${citation.fileName || 'Document'} (${citation.label || 'Source'})`;

    const snippet = document.createElement('div');
    snippet.textContent = citation.snippet || '';

    item.append(title, snippet);
    list.append(item);
  }

  box.append(list);
}
