const MAX_BYTES = 50 * 1024 * 1024;
const MAX_DURATION_SECONDS = 300;

async function checkWav(file) {
  if (file.size < 44) {
    return 'This is not a WAV file.';
  }

  const header = await file
    .slice(0, Math.min(file.size, 1024 * 1024))
    .arrayBuffer();
  const bytes = new Uint8Array(header);
  const view = new DataView(header);

  const fourCC = (offset) =>
    String.fromCharCode(...bytes.slice(offset, offset + 4));

  if (fourCC(0) !== 'RIFF' || fourCC(8) !== 'WAVE') {
    return 'This is not a WAV file.';
  }

  let offset = 12;
  let byteRate = 0;
  let dataSize = 0;
  let formatCode = 0;
  let channels = 0;
  let bitsPerSample = 0;

  while (offset + 8 <= header.byteLength) {
    const chunkId = fourCC(offset);
    const chunkSize = view.getUint32(offset + 4, true);
    const chunkStart = offset + 8;
    const chunkEnd = chunkStart + chunkSize;

    if (chunkEnd > header.byteLength || chunkEnd > file.size) {
      if (chunkId === 'data' && chunkStart <= header.byteLength) {
        dataSize = chunkSize;
        break;
      }
      return 'This is not a valid WAV file.';
    }

    if (chunkId === 'fmt ' && chunkSize >= 16) {
      formatCode = view.getUint16(chunkStart, true);
      channels = view.getUint16(chunkStart + 2, true);
      byteRate = view.getUint32(chunkStart + 8, true);
      bitsPerSample = view.getUint16(chunkStart + 14, true);
    }

    if (chunkId === 'data') {
      dataSize = chunkSize;
      break;
    }

    offset = chunkEnd + (chunkSize % 2);
  }

  if (!formatCode || !channels || !byteRate || !dataSize) {
    return 'This is not a valid WAV file.';
  }

  if (formatCode !== 1 || bitsPerSample !== 16 || channels < 1 || channels > 2) {
    return 'Unsupported WAV format. Use 16-bit PCM audio with mono or stereo channels.';
  }

  if (dataSize / byteRate > MAX_DURATION_SECONDS) {
    return 'Audio is longer than 5 minutes.';
  }

  return null;
}

export async function validateFile(file) {
  const name = file.name.toLowerCase();
  const isWav = name.endsWith('.wav');
  const isPdf = name.endsWith('.pdf');

  if (!isWav && !isPdf) {
    return 'Only .wav and .pdf files are supported. Convert other audio first.';
  }

  if (file.size > MAX_BYTES) {
    return 'File is larger than 50 MB.';
  }

  if (file.size === 0) {
    return 'File is empty.';
  }

  return isWav ? await checkWav(file) : null;
}
