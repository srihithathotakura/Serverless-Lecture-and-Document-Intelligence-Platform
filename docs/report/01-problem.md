# Problem Statement and Objectives

## 1. Problem Statement

Users log in, upload a lecture recording (WAV audio) or a text PDF, and the system processes it automatically: speech-to-text with a speech model hosted on Amazon Bedrock for audio or text extraction with pypdf for PDF, followed by chunking, summarization with a Bedrock-hosted language model, and a keyword (TF-IDF) search index. Users can read the transcript and summary, ask questions about their own uploads and receive answers with citations (timestamps for audio and page numbers for PDF). The system is serverless on AWS, and each user sees only their own data.

## 2. Requirements

3.1. Users must be able to log in to the platform.
3.2. Users must be able to upload a lecture recording in WAV format or a text PDF.
3.3. Uploaded files must be processed automatically.
3.4. The system must provide the processed transcript and summary to the user.
3.5. Users must be able to ask questions about their own uploaded documents and receive answers with citations.
3.6. Each user must only be able to access their own uploaded data.
3.7. The system may optionally provide a spoken summary using Amazon Polly after the MVP is stable.

## 3. Measurable Objectives

The MVP must demonstrate the following working capabilities: login, upload, automatic processing, transcript plus summary, Q&A with citations, and delete.

## 4. Hard Limits

- Audio must be 16-bit PCM WAV and must be no longer than 5 minutes.
- PDFs must contain real text (no scans) and must be no longer than 20 pages.
- Search is keyword-based, so a question that shares no words with the text finds nothing.
