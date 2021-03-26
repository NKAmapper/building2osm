from admin_units import linear_rings_assembler, polygon_assembler

relws = [{
	"id": 500,
	"nodes": [
		1, 2, 3
	]}, {
	"id": 502,
	"nodes": [
		5, 6, 7

	]}, {
	"id": 501,
	"nodes": [
		5, 4, 3
	]}, {
	"id": 505,
	"nodes": [
		1, 9, 7

	]}]
test_ways = {way['id']: way for way in relws}
test_nodes = {node['id']: node for node in [{
		"type": "node",
		"id": 1,
		"lat": 59.8111,
		"lon": 10.7183
	}, {
		"type": "node",
		"id": 2,
		"lat": 59.8340,
		"lon": 10.8364
	}, {
		"type": "node",
		"id": 3,
		"lat": 59.8791,
		"lon": 10.9067
	}, {
		"type": "node",
		"id": 4,
		"lat": 59.9394,
		"lon": 10.8977
	}, {
		"type": "node",
		"id": 5,
		"lat": 59.9769,
		"lon": 10.8439
	}, {
		"type": "node",
		"id": 6,
		"lat": 59.9929,
		"lon": 10.7317
	}, {
		"type": "node",
		"id": 7,
		"lat": 59.9754,
		"lon": 10.5994
	}, {
		"type": "node",
		"id": 9,
		"lat": 59.8596,
		"lon": 10.5956
}]}

relation_members = [{
		"type": "way",
		"ref": 500,
		"role": "outer"
	}, {
		"type": "way",
		"ref": 501,
		"role": "outer"
	}, {
		"type": "way",
		"ref": 502,
		"role": "outer"
	}, {
		"type": "way",
		"ref": 505,
		"role": "outer"
	}]


def test_ring():
	expected = [[1, 2, 3, 4, 5, 6, 7, 9, 1]]
	assert linear_rings_assembler(relws) == expected


def test_polygon():
	expected = [[
		(10.7183, 59.8111), (10.8364, 59.8340), (10.9067, 59.8791),
		(10.8977, 59.9394), (10.8439, 59.9769), (10.7317, 59.9929),
		(10.5994, 59.9754), (10.5956, 59.8596), (10.7183, 59.8111)
	]]

	assert polygon_assembler(relation_members, test_ways, test_nodes) == expected
