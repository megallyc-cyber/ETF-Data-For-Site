/* Licentia Pro — decides whether a page wears the paid surface.

   Entitlement comes from the account, not from the browser. The order is:

     1. app_metadata.tier   — set server side, users cannot touch it. When
                              billing exists, the payment webhook writes here
                              and this is the only branch that should remain.
     2. user_metadata.tier  — writable by the account holder, so it is a label
                              rather than a lock. Fine while Pro is being
                              fitted out; delete this branch once (1) is live.
     3. ?pro=1              — a preview for one tab only. Deliberately kept in
                              sessionStorage so it dies with the tab and can
                              never leak into a normal signed-in session.

   Anything else gets Ember. No account, no tier, no gold.  */
(function(){
  var PREVIEW = 'LICENTIA_PRO_PREVIEW';
  var URL_ = 'https://sopzbiuwakowbuqgwpmg.supabase.co';
  var KEY = 'sb_publishable_x-g6QbE71nKThHN66Mz1kQ_16NXoj5j';

  // the old persistent flag let gold stick to accounts that never paid
  try { localStorage.removeItem('LICENTIA_PRO'); } catch (e) {}

  function previewOn(){
    var q = window.location.search;
    try {
      if (/[?&]pro=1/.test(q)) { sessionStorage.setItem(PREVIEW, '1'); return true; }
      if (/[?&]pro=0/.test(q)) { sessionStorage.removeItem(PREVIEW); return false; }
      return sessionStorage.getItem(PREVIEW) === '1';
    } catch (e) { return /[?&]pro=1/.test(q); }
  }

  function apply(on){
    if (!document.body) return;
    document.body.classList.toggle('pro', !!on);
  }

  // Read the tier straight off the stored session so the page can dress itself
  // before any module finishes loading; no flash of the wrong theme.
  function tierFromStoredSession(){
    try {
      for (var i = 0; i < localStorage.length; i++){
        var k = localStorage.key(i);
        if (k.indexOf('sb-') !== 0 || k.indexOf('-auth-token') === -1) continue;
        var raw = JSON.parse(localStorage.getItem(k));
        var u = raw && (raw.user || (raw.currentSession && raw.currentSession.user));
        if (!u) continue;
        return (u.app_metadata && u.app_metadata.tier) ||
               (u.user_metadata && u.user_metadata.tier) || null;
      }
    } catch (e) {}
    return null;
  }

  function decide(){
    if (previewOn()) { apply(true); return; }
    apply(tierFromStoredSession() === 'pro');
  }

  if (document.body) decide();
  else document.addEventListener('DOMContentLoaded', decide);

  // confirm against the server, in case the stored session is stale
  window.addEventListener('load', function(){
    if (previewOn()) return;
    fetch(URL_ + '/auth/v1/user', {
      headers: { apikey: KEY, Authorization: 'Bearer ' + (function(){
        try {
          for (var i = 0; i < localStorage.length; i++){
            var k = localStorage.key(i);
            if (k.indexOf('sb-') === 0 && k.indexOf('-auth-token') > -1){
              var raw = JSON.parse(localStorage.getItem(k));
              return (raw && (raw.access_token || (raw.currentSession && raw.currentSession.access_token))) || '';
            }
          }
        } catch (e) {}
        return '';
      })() }
    }).then(function(r){ return r.ok ? r.json() : null; })
      .then(function(u){
        if (!u) { apply(false); return; }
        var tier = (u.app_metadata && u.app_metadata.tier) ||
                   (u.user_metadata && u.user_metadata.tier) || null;
        apply(tier === 'pro');
      })
      .catch(function(){});
  });
})();
