import io
import zipfile

from app.transit import _parse_gtfs


def test_parses_accessibility_and_vehicle_shape_from_gtfs_zip():
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,wheelchair_boarding\nA,Start,53.34,-6.25,1\nB,End,53.35,-6.24,1\n",
        )
        archive.writestr("routes.txt", "route_id,route_short_name\nR1,46\n")
        archive.writestr("trips.txt", "route_id,service_id,trip_id,wheelchair_accessible,shape_id\nR1,weekday,T1,1,S1\n")
        archive.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT1,09:00:00,09:00:00,A,1\nT1,09:10:00,09:10:00,B,2\n",
        )
        archive.writestr(
            "shapes.txt",
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nS1,53.34,-6.25,1\nS1,53.345,-6.245,2\nS1,53.35,-6.24,3\n",
        )

    feed = _parse_gtfs(content.getvalue())

    assert feed.stops["A"].wheelchair_boarding == "1"
    assert feed.trips["T1"].wheelchair_accessible == "1"
    assert feed.route_labels["R1"] == "46"
    assert feed.shapes_by_id["S1"][1] == [-6.245, 53.345]
