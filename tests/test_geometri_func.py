from municipality_split import inside_polygon, centroid_polygon


def test_inside_polygon_clockwise():
	polygon = [[(1., 1.), (2., 3.), (3., 1.), (1., 1.)]]
	point = (2., 2.)
	assert inside_polygon(point, polygon)


def test_inside_polygon_counter_clockwise():
	polygon = [[(3., 1.), (2., 3.), (1., 1.), (3., 1.)]]
	point = (2., 2.)
	assert inside_polygon(point, polygon)


def test_outside_polygon():
	polygon = [[(1., 1.), (2., 3.), (3., 1.), (1., 1.)]]
	point = (1., 3.)
	assert not inside_polygon(point, polygon)


def test_outside_polygon_with_hole():
	polygon = [
		[(0., 0.), (0., 5.), (5., 5.), (5., 0.), (0., 0.)],
		[(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)]
	]
	point = (2., 2.)
	assert not inside_polygon(point, polygon)


def test_centroid_polygon():
	polygon = [[(0., 0.), (3., 6.), (6., 0.), (0., 0.)]]
	point = (3., 2.)
	assert centroid_polygon(polygon) == point
