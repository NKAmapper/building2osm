.PHONY : all flake8 test


FLAKE8_FILES := \
		filter_buildings.py \
		tests/test_filter.py \
		;


all : flake8 test

flake8 : $(FLAKE8_FILES)
	flake8 $?

test :
	python3 -m unittest discover -s tests
