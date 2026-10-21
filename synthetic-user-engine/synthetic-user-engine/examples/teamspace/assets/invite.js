(function () {
  'use strict';
  var T = window.Teamspace;
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var ROLE_LABELS = { viewer: 'Viewer', contributor: 'Contributor', admin: 'Workspace admin' };

  var form = document.getElementById('invite-form');
  var step1 = document.getElementById('step-1');
  var step2 = document.getElementById('step-2');
  var ind1 = document.getElementById('step-ind-1');
  var ind2 = document.getElementById('step-ind-2');
  var email = document.getElementById('invite-email');
  var nameInput = document.getElementById('invite-name');
  var continueBtn = document.getElementById('continue-btn');
  var backBtn = document.getElementById('back-btn');
  var sendInviteBtn = document.getElementById('send-invite-btn');

  var helpBtn = document.getElementById('roles-help-btn');
  var popover = document.getElementById('roles-popover');

  var backdrop = document.getElementById('confirm-backdrop');
  var dialog = document.getElementById('confirm-dialog');
  var confirmTitle = document.getElementById('confirm-title');
  var confirmDesc = document.getElementById('confirm-desc');
  var confirmError = document.getElementById('confirm-error');
  var confirmBack = document.getElementById('confirm-back-btn');
  var confirmSend = document.getElementById('confirm-send-btn');

  var currentStep = 1;

  /* ---------- roles help popover ---------- */
  function setPopover(open) {
    popover.hidden = !open;
    helpBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  helpBtn.addEventListener('click', function (e) {
    e.preventDefault();
    setPopover(popover.hidden);
  });
  document.addEventListener('click', function (e) {
    if (!popover.hidden && !popover.contains(e.target) && !helpBtn.contains(e.target)) setPopover(false);
  });

  /* ---------- email validation ---------- */
  function emailError() {
    var v = email.value.trim();
    if (!v) return 'Enter an email address.';
    if (!EMAIL_RE.test(v)) return 'Enter a valid email address, like name@company.com.';
    return '';
  }

  function showEmailError(message) {
    var existing = document.getElementById('invite-email-error');
    if (!message) {
      if (existing) existing.remove();
      email.removeAttribute('aria-invalid');
      email.setAttribute('aria-describedby', 'invite-email-help');
      return;
    }
    if (!existing) {
      existing = document.createElement('p');
      existing.id = 'invite-email-error';
      existing.className = 'field-error';
      existing.setAttribute('role', 'alert');
      email.insertAdjacentElement('afterend', existing);
    }
    existing.textContent = message;
    email.setAttribute('aria-invalid', 'true');
    email.setAttribute('aria-describedby', 'invite-email-error invite-email-help');
  }

  email.addEventListener('input', function () {
    if (document.getElementById('invite-email-error') && !emailError()) showEmailError('');
  });

  /* ---------- steps ---------- */
  function selectedRole() {
    var r = form.querySelector('input[name="role"]:checked');
    return r ? r.value : 'contributor';
  }

  function selectedProjects() {
    return Array.prototype.map.call(form.querySelectorAll('input[name="projects"]:checked'), function (c) { return c.value; });
  }

  function goTo(step) {
    currentStep = step;
    step1.hidden = step !== 1;
    step2.hidden = step !== 2;
    ind1.classList.toggle('is-current', step === 1);
    ind1.classList.toggle('is-done', step === 2);
    ind2.classList.toggle('is-current', step === 2);
    if (step === 1) { ind1.setAttribute('aria-current', 'step'); ind2.removeAttribute('aria-current'); }
    else { ind2.setAttribute('aria-current', 'step'); ind1.removeAttribute('aria-current'); }
    setPopover(false);
    window.scrollTo(0, 0);
  }

  function tryContinue() {
    var err = emailError();
    showEmailError(err);
    if (err) { email.focus(); return; }
    var who = nameInput.value.trim() || email.value.trim();
    document.getElementById('invite-summary').textContent =
      'Inviting ' + who + ' as ' + ROLE_LABELS[selectedRole()] + '.';
    goTo(2);
    document.getElementById('step-2-title').setAttribute('tabindex', '-1');
    document.getElementById('step-2-title').focus();
  }

  continueBtn.addEventListener('click', tryContinue);
  backBtn.addEventListener('click', function () { goTo(1); continueBtn.focus(); });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (currentStep === 1) tryContinue(); else openConfirm();
  });

  /* ---------- confirmation dialog ---------- */
  function openConfirm() {
    var addr = email.value.trim();
    var projects = selectedProjects();
    confirmTitle.textContent = 'Send invite to ' + addr + '?';
    var who = nameInput.value.trim() || addr;
    confirmDesc.textContent = who + ' will join Lumen Labs as ' + ROLE_LABELS[selectedRole()] +
      (projects.length ? ' with access to ' + projects.join(', ') + '.' : ' without access to any project.');
    confirmError.hidden = true;
    confirmSend.disabled = false;
    confirmSend.textContent = 'Send';
    backdrop.hidden = false;
    document.body.classList.add('modal-open');
    confirmSend.focus();
  }

  function closeConfirm() {
    backdrop.hidden = true;
    document.body.classList.remove('modal-open');
    sendInviteBtn.focus();
  }

  sendInviteBtn.addEventListener('click', openConfirm);
  confirmBack.addEventListener('click', closeConfirm);
  backdrop.addEventListener('click', function (e) { if (e.target === backdrop) closeConfirm(); });

  dialog.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab') return;
    var items = [confirmBack, confirmSend].filter(function (b) { return !b.disabled; });
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (!backdrop.hidden) closeConfirm();
    else if (!popover.hidden) { setPopover(false); helpBtn.focus(); }
  });

  confirmSend.addEventListener('click', function () {
    confirmSend.disabled = true;
    confirmSend.textContent = 'Sending…';
    confirmError.hidden = true;
    T.api('/api/invites', {
      method: 'POST',
      body: {
        email: email.value.trim(),
        name: nameInput.value.trim(),
        role: selectedRole(),
        projects: selectedProjects(),
        welcomeEmail: document.getElementById('welcome-email').checked
      }
    }).then(function () {
      location.href = '/members?invite=sent';
    }).catch(function (err) {
      confirmError.textContent = err.message;
      confirmError.hidden = false;
      confirmSend.disabled = false;
      confirmSend.textContent = 'Send';
    });
  });
})();
