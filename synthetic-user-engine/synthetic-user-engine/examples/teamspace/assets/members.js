(function () {
  'use strict';
  var T = window.Teamspace;
  var body = document.getElementById('members-body');
  var search = document.getElementById('member-search');
  var summary = document.getElementById('member-summary');
  var members = [];

  var params = new URLSearchParams(location.search);
  if (params.get('invite') === 'sent') {
    T.toast('Invite sent', 4000);
    history.replaceState(null, '', '/members');
  }

  function badge(status) {
    var cls = status === 'Active' ? 'badge-active' : status === 'Invited' ? 'badge-invited' : 'badge-muted';
    return '<span class="badge ' + cls + '">' + T.escapeHtml(status) + '</span>';
  }

  function render() {
    var q = search.value.trim().toLowerCase();
    var rows = members.filter(function (m) {
      return !q || m.name.toLowerCase().indexOf(q) !== -1 || m.email.toLowerCase().indexOf(q) !== -1;
    });
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="5" class="muted">No members match “' + T.escapeHtml(search.value) + '”.</td></tr>';
    } else {
      body.innerHTML = rows.map(function (m) {
        return '<tr>' +
          '<td><div class="person"><span class="avatar avatar-sm" aria-hidden="true">' + T.escapeHtml(T.initials(m.name)) + '</span><span class="cell-title">' + T.escapeHtml(m.name) + '</span></div></td>' +
          '<td>' + T.escapeHtml(m.email) + '</td>' +
          '<td>' + T.escapeHtml(m.roleLabel) + '</td>' +
          '<td>' + badge(m.status) + '</td>' +
          '<td class="muted">' + T.escapeHtml(m.lastActive) + '</td>' +
          '</tr>';
      }).join('');
    }
    var invited = members.filter(function (m) { return m.status === 'Invited'; }).length;
    summary.textContent = members.length + ' people' + (invited ? ' · ' + invited + ' invited' : '');
    document.getElementById('member-count').textContent = members.length;
  }

  search.addEventListener('input', render);

  T.api('/api/members').then(function (data) {
    members = data.members;
    render();
  }).catch(function (err) {
    body.innerHTML = '<tr><td colspan="5" class="muted">' + T.escapeHtml(err.message) + '</td></tr>';
  });
})();
