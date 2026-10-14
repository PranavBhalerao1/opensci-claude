(function(){
  "use strict";
  var app = window.OpenScientist = window.OpenScientist || {};

  app.initNavigation = function initNavigation(){
    var nav = document.getElementById('siteNav');
    if(!nav) return;
    var praxisSection = document.getElementById('praxis');

    function update(){
      if(document.documentElement.scrollTop > 30) nav.classList.add('scrolled');
      else nav.classList.remove('scrolled');

      if(praxisSection){
        var praxisTop = praxisSection.offsetTop;
        var praxisBottom = praxisTop + praxisSection.offsetHeight;
        var scrollPos = document.documentElement.scrollTop + nav.offsetHeight;

        if(scrollPos >= praxisTop && scrollPos < praxisBottom){
          nav.classList.add('in-praxis');
        } else {
          nav.classList.remove('in-praxis');
        }
      }
    }
    document.addEventListener('scroll', update, {passive:true});
    update();
  };
})();
