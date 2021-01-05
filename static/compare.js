function fallbackMessage(action) {
	var actionMsg = '';
	var actionKey = (action === 'cut' ? 'X' : 'C');
	if (/iPhone|iPad/i.test(navigator.userAgent)) {
		actionMsg = 'No support :(';
	} else if (/Mac/i.test(navigator.userAgent)) {
		actionMsg = 'Press ⌘-' + actionKey + ' to ' + action;
	} else {
		actionMsg = 'Press Ctrl-' + actionKey + ' to ' + action;
	}
	return actionMsg;
}
$(document).ready(function(){
   setTimeout(function(){
      $('.ds-selector-tabs .selectors a').click(function() {
        var $this = $(this);
        var $p = $this.parents('.ds-selector-tabs');
        $('.selected', $p).removeClass('selected');
        $this.addClass('selected');
		var $selectorpanel = $('.ds-selection.' + $this.data('selects'), $p)
        $selectorpanel.addClass('selected');
      });
    }, 0);
	
	clip = new ClipboardJS('.clip');
	clip.on('success', function(e) {
		var tip = $('.tooltip .tooltiptext');
		tip.text('Copied!');
		tip.addClass('show');
	    e.clearSelection();
        setTimeout(function(targ) {
            targ.removeClass('show');
        }, 5000);
	});

	clip.on('error', function(e) {
		var tip = $('.tooltip .tooltiptext');
		tip.text(fallbackMessage('copy'));
		tip.addClass('show');
	});
	$('.tooltip .tooltiptext').mouseleave(function(){
		$(this).removeClass('show');
	});
});

function hideData(form){
    $('.data').addClass('hidden')
    $('.spinner').addClass('showSpinner')
    return true
}
