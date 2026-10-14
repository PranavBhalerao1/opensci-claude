(function(){
  "use strict";
  window.OpenScientist = window.OpenScientist || {};

  document.addEventListener('DOMContentLoaded', function(){
    var app = window.OpenScientist;
    document.body.classList.add('loaded');
    app.initNavigation?.();
    app.initScrollProgress?.();
    app.initReveal?.();
    app.initDemo?.();
  });
})();
