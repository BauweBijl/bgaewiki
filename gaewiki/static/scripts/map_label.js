google.maps.event.addDomListener(window, 'load', function () {
	var sw = new google.maps.LatLng(map_data.bounds.minlat, map_data.bounds.minlng);
	var ne = new google.maps.LatLng(map_data.bounds.maxlat, map_data.bounds.maxlng);
	var bounds = new google.maps.LatLngBounds(sw, ne);

	var map = new google.maps.Map(document.getElementById("map_canvas"), {
		zoom: 2,
		center: bounds.getCenter(),
		mapTypeId: google.maps.MapTypeId.HYBRID
	});

	var iw = new google.maps.InfoWindow({
		maxWidth: 300
	});

	for (var idx = 0; idx < map_data.markers.length; idx++) {
		add_marker(map, map_data.markers[idx], iw);
	}

	var ctl = document.getElementById('popout');
	if (ctl) {
		google.maps.event.addDomListener(ctl, 'click', function () {
			window.open(window.location.href);
		});
		map.controls[google.maps.ControlPosition.TOP_RIGHT].push(ctl);
	}

	map.panToBounds(bounds);
	map.fitBounds(bounds);
});

function add_marker(map, s, iw)
{
	var marker = new google.maps.Marker({
		map: map,
		position: new google.maps.LatLng(s.lat, s.lng),
		title: s.title
	});

	google.maps.event.addListener(marker, 'click', function () {
		iw.setContent(s.html);
		iw.open(map, marker);
	});
}
