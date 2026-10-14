(function(){
  "use strict";
  var app = window.OpenScientist = window.OpenScientist || {};

  app.initScrollProgress = function initScrollProgress(){
    var progress = document.getElementById('progress');
    if(!progress) return;
    function update(){
      var root = document.documentElement;
      var height = root.scrollHeight - root.clientHeight;
      progress.style.width = (height ? root.scrollTop / height * 100 : 0) + '%';
    }
    document.addEventListener('scroll', update, {passive:true});
    update();
  };
})();
