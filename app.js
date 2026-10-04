const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const toast = (message) => {
  const node = $('#toast');
  node.textContent = message;
  node.classList.add('show');
  setTimeout(() => node.classList.remove('show'), 3000);
};

const auth = $('#auth');
const closeAuth = () => { auth.hidden = true; auth.style.display = 'none'; };
auth.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') return closeAuth();
  if (event.key !== 'Tab') return;
  const controls = [...auth.querySelectorAll('button, input, [href]')];
  const first = controls[0];
  const last = controls.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
$('#closeAuth').addEventListener('click', closeAuth);
$$('.oauth').forEach((button) => button.addEventListener('click', () => { closeAuth(); toast(`Mock ${button.dataset.provider} sign-in complete. Welcome, Aoife.`); }));
$('#continue').addEventListener('click', () => { closeAuth(); toast('Mock sign-in complete. Welcome, Aoife.'); });

const settings = $('#settings');
const openSettings = () => { settings.hidden = false; $('#settingsButton').setAttribute('aria-expanded', 'true'); $('#closeSettings').focus(); };
const closeSettings = () => { settings.hidden = true; $('#settingsButton').setAttribute('aria-expanded', 'false'); $('#settingsButton').focus(); };
$('#settingsButton').addEventListener('click', () => settings.hidden ? openSettings() : closeSettings());
$('#profileButton').addEventListener('click', openSettings);
$('#editProfile').addEventListener('click', openSettings);
$('#closeSettings').addEventListener('click', closeSettings);

const toggle = (id, className) => $(id).addEventListener('click', () => {
  const button = $(id); const on = button.getAttribute('aria-checked') !== 'true';
  button.setAttribute('aria-checked', String(on)); button.classList.toggle('on', on);
  if (className) document.body.classList.toggle(className, on);
});
toggle('#contrastToggle', 'high-contrast'); toggle('#voiceToggle');
$('#fontUp').addEventListener('click', () => { document.body.classList.add('font-large'); $('#fontStatus').textContent = 'Large'; });
$('#fontDown').addEventListener('click', () => { document.body.classList.remove('font-large'); $('#fontStatus').textContent = 'Standard'; });
$('#clearSearch').addEventListener('click', () => { $('#search').value = ''; $('#search').focus(); });
$$('.chips button').forEach((button) => button.addEventListener('click', () => toast(`Showing nearby ${button.textContent.toLowerCase()} with access facts.`)));
$$('.pin').forEach((pin) => pin.addEventListener('click', () => toast(pin.getAttribute('aria-label'))));
$('.save').addEventListener('click', (event) => { const saved = event.currentTarget.textContent === '♥'; event.currentTarget.textContent = saved ? '♡' : '♥'; toast(saved ? 'Removed from saved places.' : 'Saved to your trusted places.'); });
$('#listView').addEventListener('click', () => toast('List view would show the same place facts without using the map.'));
$('#report').addEventListener('click', () => toast('Barrier reporting is ready for the next front-end screen.'));
$('#reportSmall').addEventListener('click', () => toast('Thank you. A report flow would record the change and any supporting evidence.'));
