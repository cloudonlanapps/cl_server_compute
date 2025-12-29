# Task Server Tests

## Prerequisites

- Python 3.12+
- uv package manager

## Running Tests

### Quick Start

```bash
# Install dependencies (if not already installed)
uv sync --all-extras

# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov

# Run without coverage (faster)
uv run pytest --no-cov
```

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_routes.py           # API endpoint tests
├── test_service.py          # Service layer tests
├── test_capability.py       # Capability manager tests
└── test_integration.py      # Integration tests
```

### Running Specific Tests

```bash
# Run specific test file
uv run pytest tests/test_routes.py -v

# Run specific test function
uv run pytest tests/test_routes.py::test_get_job -v

# Run tests matching pattern
uv run pytest -k "job" -v

# Skip integration tests
uv run pytest -m "not integration"
```

## Coverage Requirements

- Minimum coverage: 90%
- Coverage reports generated in `htmlcov/`
- View report: open `htmlcov/index.html`

## Writing Tests

### Test Structure

```python
def test_feature_name():
    # Arrange - set up test data
    # Act - execute the code being tested
    # Assert - verify the results
    pass
```

### Using Fixtures

```python
def test_with_db(db_session):
    # db_session provided by conftest.py
    pass
```

## Example Commands

```bash
# Run all tests with verbose output
uv run pytest -v

# Run only unit tests (fast)
uv run pytest tests/test_service.py -v

# Run with coverage and generate HTML report
uv run pytest --cov=task_server --cov-report=html

# Run and show print statements
uv run pytest -s

# Run and stop at first failure
uv run pytest -x

# Run last failed tests only
uv run pytest --lf
```
