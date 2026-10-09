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
        <p>Welcome back. Your authenticated workspace is ready.</p>
        <div class="welcome-card">
          <h2>Welcome to Lectura</h2>
          <p>Your account is signed in successfully. Document listing, uploads, and question answering will be connected when the API endpoints are available.</p>
          <p id="api-status" style="margin-top:12px"></p>
        </div>
      </section>
    </main>`;

  document.querySelector('#logout-button').addEventListener('click', () => {
    signOut();
    mode = 'signin';
    renderAuth();
  });
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
