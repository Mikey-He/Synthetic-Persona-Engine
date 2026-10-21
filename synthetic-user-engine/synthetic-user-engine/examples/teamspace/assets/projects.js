(function () {
  'use strict';
  var T = window.Teamspace;
  var body = document.getElementById('projects-body');

  T.api('/api/projects').then(function (data) {
    body.innerHTML = data.projects.map(function (p) {
      return '<tr>' +
        '<td><div class="cell-title">' + T.escapeHtml(p.name) + '</div><div class="helper">' + T.escapeHtml(p.description) + '</div></td>' +
        '<td>' + T.escapeHtml(p.owner) + '</td>' +
        '<td>' + T.escapeHtml(p.members) + '</td>' +
        '<td>' + T.escapeHtml(p.updated) + '</td>' +
        '</tr>';
    }).join('');
  }).catch(function (err) {
    body.innerHTML = '<tr><td colspan="4" class="muted">' + T.escapeHtml(err.message) + '</td></tr>';
  });
})();
