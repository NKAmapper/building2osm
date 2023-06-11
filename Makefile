.PHONY : all flake8 test


FLAKE8_FILES := \
		filter_buildings.py \
		find_lifecycle_updates.py \
		find_removed.py \
		shared.py \
		tests/test_filter.py \
		tests/test_find_lifecycle_updates.py \
		tests/test_find_removed.py \
		tests/test_shared.py \
		;


all : flake8 test

flake8 : $(FLAKE8_FILES)
	flake8 $?

test :
	python3 -m unittest discover -s tests