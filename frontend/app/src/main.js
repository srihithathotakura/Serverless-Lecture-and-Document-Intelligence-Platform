import { uploadFile } from './upload.js';
import { refreshList, stopPolling } from './docs.js';
import { showDetail } from './detail.js';
import { ask, renderAnswer } from './ask.js';
import './style.css';
import {
  signUp,
  confirmSignUp,
  signIn,
  signOut,
  getIdToken,
  getCurrentUser
} from './auth.js';

const app = document.querySelector('#app');
let mode = 'signin';
let pendingEmail = '';
let pendingPassword = '';

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;'
  })[char]);
}

function showMessage(message, type = 'error') {
  const box = document.querySelector('#message');
  if (!box) return;
  box.textContent = message;
  box.className = `message visible ${type}`;
}

function setBusy(busy) {
  const button = document.querySelector('#submit-button');
  if (button) {
    button.disabled = busy;
    button.textContent = busy ? 'Please wait…' : button.dataset.label;
  }
}

function renderAuth() {
  const isSignup = mode === 'signup';
  const isConfirm = mode === 'confirm';

  app.innerHTML = `
    <main class="auth-layout">
      <section class="brand-panel">
        <div class="brand">
          <span class="brand-mark">L</span>
          <span>Lectura</span>
        </div>
        <div class="brand-copy">
          <span class="eyebrow"><span class="eyebrow-dot"></span> YOUR LEARNING WORKSPACE</span>
          <h1>Knowledge is everywhere. <span>Find it faster.</span></h1>
          <p>One intelligent workspace for your lectures and study materials. Search, understand, and revisit the knowledge that matters.</p>
          <div class="feature-list">
            <div class="feature"><span class="feature-icon">▤</span><span>Bring your lecture materials together</span></div>
            <div class="feature"><span class="feature-icon">✳</span><span>Discover key ideas and concise summaries</span></div>
            <div class="feature"><span class="feature-icon">⌕</span><span>Find answers grounded in your content</span></div>
          </div>
        </div>
        <div class="brand-footer">A smarter way to revisit what you learn.</div>
      </section>

      <section class="form-panel">
        <div class="form-wrap">
          <div class="mobile-brand"><span class="brand-mark">L</span> Lectura</div>
          <div class="form-heading">
            <h2>${isConfirm ? 'Verify your email' : isSignup ? 'Create your account' : 'Welcome back'}</h2>
            <p>${isConfirm ? `Enter the confirmation code sent to ${escapeHtml(pendingEmail)}.` : isSignup ? 'Create an account to get started with your learning workspace.' : 'Sign in to continue to your learning workspace.'}</p>
          </div>

          <div id="message" class="message" role="status" aria-live="polite"></div>

          ${!isConfirm ? `
            <div class="mode-switch">
              <button type="button" class="mode-button ${!isSignup ? 'active' : ''}" id="signin-tab">Sign in</button>
              <button type="button" class="mode-button ${isSignup ? 'active' : ''}" id="signup-tab">Create account</button>
            </div>` : ''}

          <form id="auth-form">
            ${isConfirm ? `
              <div class="field">
                <label for="code">Email confirmation code</label>
                <input id="code" name="code" autocomplete="one-time-code" required placeholder="Enter the code" />
              </div>
            ` : `
              <div class="field">
                <label for="email">Email address</label>
                <input id="email" name="email" type="email" autocomplete="email" required placeholder="you@example.com" value="${escapeHtml(isSignup ? pendingEmail : '')}" />
              </div>
              <div class="field">
                <label for="password">Password</label>
                <input id="password" name="password" type="password" autocomplete="${isSignup ? 'new-password' : 'current-password'}" minlength="8" required placeholder="At least 8 characters" />
              </div>
            `}
            <button class="primary-button" id="submit-button" type="submit" data-label="${isConfirm ? 'Confirm email' : isSignup ? 'Create account' : 'Sign in'}">${isConfirm ? 'Confirm email' : isSignup ? 'Create account' : 'Sign in'}</button>
          </form>
          <p class="form-note">By continuing, you agree to use this workspace responsibly. <br/><strong>Your account is secured with Amazon Cognito.</strong></p>
        </div>
      </section>
    </main>`;

  document.querySelector('#signin-tab')?.addEventListener('click', () => {
    mode = 'signin';
    renderAuth();
  });

  document.querySelector('#signup-tab')?.addEventListener('click', () => {
    mode = 'signup';
    renderAuth();
  });

  document.querySelector('#auth-form').addEventListener('submit', handleSubmit);
}

async function handleSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  setBusy(true);

  try {
    if (mode === 'confirm') {
      await confirmSignUp(pendingEmail, String(data.get('code')).trim());
      mode = 'signin';
      renderAuth();
      showMessage('Email confirmed. You can now sign in.', 'success');
      return;
    }

    const email = String(data.get('email')).trim().toLowerCase();
    const password = String(data.get('password'));

    if (mode === 'signup') {
      pendingEmail = email;
      pendingPassword = password;
      await signUp(email, password);
      mode = 'confirm';
      renderAuth();
      showMessage('A confirmation code has been sent to your email.', 'success');
      return;
    }

    await signIn(email, password);
    pendingPassword = '';
    await getIdToken();
    renderDashboard(email);
  } catch (error) {
    showMessage(error?.message || 'Something went wrong. Please try again.');
  } finally {
    setBusy(false);
  }
}

function renderDashboard(email) {
  stopPolling();

  app.innerHTML = `
    <main class="dashboard">
      <header class="topbar">
        <div class="brand"><span class="brand-mark">L</span><span>Lectura</span></div>
        <div class="user-area">
          <span class="user-email">${escapeHtml(email)}</span>
          <button id="logout-button" class="secondary-button" type="button">Sign out</button>
        </div>
      </header>

      <section class="dashboard-content">
        <h1>Your learning workspace</h1>
        <p>Upload lectures and documents, track processing, and review their contents.</p>

        <section class="upload-card">
          <h2>Upload a document</h2>
          <p>WAV audio (16-bit PCM, up to 5 minutes) or a text PDF (up to 20 pages, no scans). Convert other audio first.</p>
          <div class="upload-controls">
            <input id="file-input" type="file" accept=".wav,.pdf">
            <button id="upload-button" class="primary-button" type="button">Upload</button>
          </div>
          <p id="upload-status" role="status" aria-live="polite"></p>
        </section>

        <section class="documents-card">
          <div class="section-heading">
            <h2>Your documents</h2>
            <button id="refresh-button" class="secondary-button" type="button">Refresh</button>
          </div>
          <p id="list-error" class="error" role="status" aria-live="polite"></p>
          <div class="table-wrapper">
            <table class="document-table">
              <thead>
                <tr>
                  <th>File name</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Processing step</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody id="document-list"></tbody>
            </table>
          </div>
        </section>

        <section class="ask-card">
          <h2>Ask your documents</h2>
          <p>Use words that appear in your document. Search is keyword-based.</p>
          <label for="ask-document">Search in</label>
          <select id="ask-document" required>
            <option value="">Select a completed document</option>
          </select>
          <label for="ask-question">Your question</label>
          <textarea id="ask-question" rows="3" placeholder="Ask a question about your documents"></textarea>
          <button id="ask-button" class="primary-button" type="button">Ask</button>
          <p id="ask-status" role="status" aria-live="polite"></p>
          <div id="ask-answer" aria-live="polite"></div>
        </section>

        <section id="detail-view" class="detail-card" hidden></section>
      </section>
    </main>`;

  const tbody = document.querySelector('#document-list');
  const errorEl = document.querySelector('#list-error');
  const detailBox = document.querySelector('#detail-view');
  const uploadCard = document.querySelector('.upload-card');
  const documentsCard = document.querySelector('.documents-card');
  const askCard = document.querySelector('.ask-card');
  const fileInput = document.querySelector('#file-input');
  const uploadButton = document.querySelector('#upload-button');
  const uploadStatus = document.querySelector('#upload-status');
  const askQuestion = document.querySelector('#ask-question');
  const askDocument = document.querySelector('#ask-document');
  const askButton = document.querySelector('#ask-button');
  const askStatus = document.querySelector('#ask-status');
  const askAnswer = document.querySelector('#ask-answer');

  async function loadAskDocuments() {
    try {
      const { documents } = await (await import('./api.js')).api('/documents');
      const selected = askDocument.value;
      askDocument.replaceChildren(new Option('Select a completed document', ''));

      for (const doc of documents.filter((item) => item.status === 'DONE')) {
        askDocument.add(new Option(doc.fileName, doc.documentId));
      }

      if ([...askDocument.options].some((option) => option.value === selected)) {
        askDocument.value = selected;
      }
    } catch {
      // The main document list displays its own refresh errors.
    }
  }

  askButton.addEventListener('click', async () => {
    const question = askQuestion.value.trim();

    if (!question) {
      askStatus.textContent = 'Please type a question.';
      askStatus.className = 'error';
      askQuestion.focus();
      return;
    }

    if (!askDocument.value) {
      askStatus.textContent = 'Please select a completed document.';
      askStatus.className = 'error';
      askDocument.focus();
      return;
    }

    askButton.disabled = true;
    askStatus.textContent = 'Searching… (this can take up to 30 seconds)';
    askStatus.className = '';
    askAnswer.replaceChildren();

    try {
      const response = await ask(question, askDocument.value);
      renderAnswer(askAnswer, response);
      askStatus.textContent = '';
    } catch (error) {
      askStatus.className = 'error';
      if (error?.name === 'TimeoutError' || error?.name === 'AbortError') {
        askStatus.textContent = 'The request took too long. Try a shorter question.';
      } else {
        askStatus.textContent = error?.message || 'Something went wrong. Please try again.';
      }
    } finally {
      askButton.disabled = false;
    }
  });

  loadAskDocuments();


  const refresh = () => refreshList(tbody, errorEl, openDocument);

  async function openDocument(documentId) {
    stopPolling();
    uploadCard.hidden = true;
    documentsCard.hidden = true;
    askCard.hidden = true;
    detailBox.hidden = false;

    await showDetail(detailBox, documentId, () => {
      detailBox.hidden = true;
      uploadCard.hidden = false;
      documentsCard.hidden = false;
      askCard.hidden = false;
      refresh();
    });
  }

  document.querySelector('#refresh-button').addEventListener('click', refresh);

  uploadButton.addEventListener('click', async () => {
    const file = fileInput.files[0];

    if (!file) {
      uploadStatus.textContent = 'Choose a WAV or PDF file first.';
      uploadStatus.className = 'error';
      return;
    }

    uploadButton.disabled = true;
    uploadStatus.className = '';

    try {
      await uploadFile(file, (message) => {
        uploadStatus.textContent = message;
        uploadStatus.className = '';
      });

      await refresh();
    } catch (error) {
      uploadStatus.textContent = error?.message || 'Upload failed. Please try again.';
      uploadStatus.className = 'error';
    } finally {
      uploadButton.disabled = false;
      fileInput.value = '';
    }
  });

  document.querySelector('#logout-button').addEventListener('click', () => {
    stopPolling();
    signOut();
    mode = 'signin';
    renderAuth();
  });

  refresh();
}
async function initialize() {
  try {
    const user = getCurrentUser();
    if (user) {
      await getIdToken();
      renderDashboard(user.getUsername());
      return;
    }
  } catch {
    signOut();
  }
  renderAuth();
}

initialize();
