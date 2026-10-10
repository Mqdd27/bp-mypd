
$( document ).ready(function() {
    $(".content_js").css("visibility", "hidden");
});

$('.print_js').click(PrintAsset)
// $(document).on('click', '.print_js', PrintAsset);

function PrintAsset() {
  const content = $('.content_js').text()
  printJS({printable: content, type: 'pdf', base64: true})
}
