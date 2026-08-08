// Small helpers with no opinion about the page.

export function escH(value) {
  if (value == null) return '';
  return String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export const byId = id => document.getElementById(id);

export function setStatus(message) {
  const el = byId('topbar-status');
  if (el) el.textContent = message;
}

export function setTab(id, html) {
  const el = byId(id);
  if (el) el.innerHTML = html;
}

export function markTab(buttonId) {
  const el = byId(buttonId);
  if (el) el.classList.add('has-content');
}

// innerHTML does not run <script> tags, and the step navigator ships one.
export function execScripts(container) {
  if (!container) return;
  container.querySelectorAll('script').forEach(source => {
    const script = document.createElement('script');
    script.textContent = source.textContent;
    document.body.appendChild(script);
    document.body.removeChild(script);
  });
}

export async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return response.json();
}

export function copyText(preId, button) {
  const el = byId(preId);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(() => {
    if (!button) return;
    const original = button.textContent;
    button.textContent = 'Copied!';
    button.classList.add('copied');
    setTimeout(() => {
      button.textContent = original;
      button.classList.remove('copied');
    }, 1500);
  }).catch(() => {
    if (button) button.textContent = 'Copy failed';
  });
}
