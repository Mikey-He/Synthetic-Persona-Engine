(function () {
  'use strict';
  var T = window.Teamspace;

  Promise.all([T.api('/api/members'), T.api('/api/invites'), T.api('/api/projects')]).then(function (r) {
    var members = r[0].members;
    var active = members.filter(function (m) { return m.status === 'Active'; }).length;
    var pending = r[1].invites.filter(function (i) { return i.status === 'Invited'; }).length;
    var seats = members.filter(function (m) { return m.status !== 'Inactive'; }).length;
    document.getElementById('stat-members').textContent = active;
    document.getElementById('stat-invites').textContent = pending;
    document.getElementById('stat-projects').textContent = r[2].projects.length;
    document.getElementById('stat-seats').textContent = seats;
    document.getElementById('seat-meter').style.width = Math.min(100, seats * 10) + '%';
  }).catch(function () { /* leave placeholders */ });
})();
