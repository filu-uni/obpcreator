PACKAGE_NAME := obpcreator

# Default target
all: reinstall

# Clean previous build artifacts
clean:
	rm -rf build dist *.egg-info __pycache__

# Build the package using the pyproject.toml file
build: clean
	python -m build

# Uninstall and reinstall the package from the new build
reinstall: build
	pip uninstall -y $(PACKAGE_NAME) || true
	pip install dist/*.whl

.PHONY: all clean build reinstall

