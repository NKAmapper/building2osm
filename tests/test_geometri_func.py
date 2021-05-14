from municipality_split import centroid_polygon, inside_polygon


def test_inside_polygon_clockwise():
    polygon = [[(1.0, 1.0), (2.0, 3.0), (3.0, 1.0), (1.0, 1.0)]]
    point = (2.0, 2.0)
    assert inside_polygon(point, polygon)


def test_inside_polygon_counter_clockwise():
    polygon = [[(3.0, 1.0), (2.0, 3.0), (1.0, 1.0), (3.0, 1.0)]]
    point = (2.0, 2.0)
    assert inside_polygon(point, polygon)


def test_outside_polygon():
    polygon = [[(1.0, 1.0), (2.0, 3.0), (3.0, 1.0), (1.0, 1.0)]]
    point = (1.0, 3.0)
    assert not inside_polygon(point, polygon)


def test_outside_polygon_with_hole():
    polygon = [
        [(0.0, 0.0), (0.0, 5.0), (5.0, 5.0), (5.0, 0.0), (0.0, 0.0)],
        [(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)],
    ]
    point = (2.0, 2.0)
    assert not inside_polygon(point, polygon)


def test_centroid_polygon():
    polygon = [[(0.0, 0.0), (3.0, 6.0), (6.0, 0.0), (0.0, 0.0)]]
    point = (3.0, 2.0)
    assert centroid_polygon(polygon) == point
