function show_map()
{
	var myLatlng = new google.maps.LatLng(49.496675,-102.65625);

	var myOptions = {
		zoom: 2,
		center: myLatlng,
		mapTypeId: google.maps.MapTypeId.SATELLITE
	}

	var map = new google.maps.Map(document.getElementById("map_canvas"), myOptions);

	var georssLayer = new google.maps.KmlLayer(rss_url);
	georssLayer.setMap(map);
}
