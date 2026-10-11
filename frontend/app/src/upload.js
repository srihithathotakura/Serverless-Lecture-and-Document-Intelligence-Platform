import { api } from './api.js';
import { validateFile } from './wav.js';

export async function uploadFile(file, setStatus) {
  const problem = await validateFile(file);
  if (problem) throw new Error(problem);

  const type = file.type || 'application/octet-stream';

  setStatus('Requesting upload…');

  const r = await api('/uploads', {
    method: 'POST',
    body: JSON.stringify({
      fileName: file.name,
      contentType: type,
    }),
  });

  setStatus('Uploading ' + file.name + '…');

  const put = await fetch(r.uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': type },
    body: file,
  });

  if (!put.ok) {
    throw new Error('Upload failed (' + put.status + ').');
  }

  setStatus('Upload complete. Processing starts automatically.');
}
