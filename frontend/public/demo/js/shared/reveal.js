(function(){
  "use strict";
  var app = window.OpenScientist = window.OpenScientist || {};

  app.initReveal = function initReveal(){
    var elements = document.querySelectorAll('.reveal');
    if(!elements.length) return;
    if(!('IntersectionObserver' in window)){
      elements.forEach(function(element){ element.classList.add('in'); });
      return;
    }
    var observer = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if(entry.isIntersecting){
          entry.target.classList.add('in');
          observer.unobserve(entry.target);
        }
      });
    }, {threshold:0.15, rootMargin:'0px 0px -60px 0px'});
    elements.forEach(function(element){ observer.observe(element); });
  };
})();
