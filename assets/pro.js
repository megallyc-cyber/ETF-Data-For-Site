/* Licentia Pro — decides whether a page wears the paid surface.

   Entitlement is not settled here. This only reflects a decision made
   elsewhere: ?pro=1 for previewing before billing exists, and a remembered
   flag so the treatment survives navigation between pages. When real billing
   lands, replace shouldWearPro() with a check against the account's
   entitlement and delete the query-string branch.  */
(function(){
  var KEY = 'LICENTIA_PRO';

  function remember(on){
    try { on ? localStorage.setItem(KEY, '1') : localStorage.removeItem(KEY); }
    catch (e) {}
  }

  function shouldWearPro(){
    var q = window.location.search;
    if (/[?&]pro=1/.test(q)) { remember(true);  return true; }
    if (/[?&]pro=0/.test(q)) { remember(false); return false; }
    try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; }
  }

  function apply(){
    if (document.body && shouldWearPro()) document.body.classList.add('pro');
  }

  if (document.body) apply();
  else document.addEventListener('DOMContentLoaded', apply);
})();
