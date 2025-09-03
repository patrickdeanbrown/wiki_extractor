# Development Setup

Comprehensive guide for setting up a development environment for wikibee.

## Quick Setup

```bash
# Clone the repository
git clone https://github.com/patrickdeanbrown/wikibee.git
cd wikibee

# Set up development environment
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify setup
pytest -q
ruff check .
wikibee --help
```

## Detailed Setup Instructions

### Prerequisites

**Required:**
- Python 3.8 or higher (3.12 recommended for development)
- Git
- uv (recommended) or pip

**Optional but recommended:**
- pipx for testing installation
- make for convenience commands

### Installation Methods

#### Method 1: Using uv (Recommended)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv --python 3.12
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"
```

#### Method 2: Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Upgrade pip and install
pip install --upgrade pip
pip install -e ".[dev]"
```

### Development Dependencies

The `[dev]` extra includes:
- **pytest**: Testing framework
- **requests-mock**: HTTP request mocking
- **ruff**: Linting and formatting
- **pre-commit**: Git hook management

## Development Environment

### Directory Structure

```
wikibee/
├── wikibee/           # Main package
│   ├── __init__.py    # Package exports
│   ├── cli.py         # Command-line interface
│   ├── client.py      # Wikipedia API client
│   ├── formatting.py  # Text processing
│   └── tts_*.py       # TTS-related modules
├── tests/             # Test suite
├── docs/              # Documentation
├── scripts/           # Development utilities
├── extract.py         # Backward compatibility shim
├── pyproject.toml     # Project configuration
└── CONTRIBUTING.md    # Contribution guidelines
```

### Code Style and Standards

wikibee follows these standards:
- **PEP 8** for Python code style
- **88 character** line length (enforced by ruff)
- **Type hints** for all public functions
- **Docstrings** for all public APIs (Google style)

### Pre-commit Hooks

Pre-commit hooks automatically format and lint code:

```bash
# Install hooks (one-time setup)
pre-commit install

# Run hooks manually
pre-commit run --all-files

# Skip hooks for emergency commits (not recommended)
git commit --no-verify -m "Emergency fix"
```

Configured hooks:
- **ruff**: Linting and auto-fixing
- **black**: Code formatting  
- **isort**: Import sorting
- **trailing whitespace**: Remove trailing spaces
- **end-of-file-fixer**: Ensure files end with newlines

## Testing

### Running Tests

```bash
# Quick test run (recommended for development)
pytest -q

# Verbose output with coverage
pytest -v --cov=wikibee

# Run specific test file
pytest tests/test_client.py -v

# Run tests matching pattern
pytest -k "test_search" -v

# Run with coverage report
pytest --cov=wikibee --cov-report=html
```

### Test Structure

```
tests/
├── test_cli.py           # CLI interface tests
├── test_client.py        # Wikipedia client tests  
├── test_formatting.py    # Text processing tests
├── test_extract.py       # Legacy extract.py tests
├── test_tts_*.py        # TTS-related tests
└── conftest.py          # Test configuration and fixtures
```

### Writing Tests

Example test structure:

```python
import pytest
from unittest.mock import Mock, patch
from wikibee.client import WikiClient

class TestWikiClient:
    def test_search_success(self):
        """Test successful search operation."""
        client = WikiClient()
        
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'query': {
                    'search': [
                        {'title': 'Test Article', 'snippet': 'Test snippet'}
                    ]
                }
            }
            mock_get.return_value = mock_response
            
            results = client.search('test')
            
            assert len(results) == 1
            assert results[0]['title'] == 'Test Article'
```

### Test Coverage

Maintain high test coverage:
- **Minimum**: 80% overall coverage
- **Target**: 90%+ for core functionality
- **Critical paths**: 100% coverage for CLI and client modules

## Code Quality

### Linting and Formatting

```bash
# Check code style
ruff check .

# Auto-fix issues
ruff check . --fix

# Check specific file
ruff check wikibee/cli.py
```

### Type Checking

Type hints are required and enforced via `mypy` in CI:

```python
# Good: Type hints included
def extract_text(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """Extract text from Wikipedia URL."""
    pass

```bash
mypy wikibee
```

Bad: No type hints
```python
def extract_text(url, timeout=15):
    ...
```
```

### Documentation

All public functions need docstrings:

```python
def search_articles(term: str, limit: int = 10) -> list[dict]:
    """Search for Wikipedia articles.
    
    Args:
        term: Search term to query
        limit: Maximum number of results to return
        
    Returns:
        List of article dictionaries with title, snippet, and URL
        
    Raises:
        NetworkError: If the request fails
        APIError: If the API returns invalid data
    """
    pass
```

## Debugging

### Debug Mode

Enable verbose output for debugging:

```bash
# CLI debugging
wikibee "test topic" --verbose

# Python debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Common Debug Scenarios

**Network Issues:**
```python
import requests
import logging

# Enable requests debugging
logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)
```

**API Response Issues:**
```python
# Add debug prints to client.py
def search(self, term: str) -> list[dict]:
    response = self.session.get(url, params=params)
    print(f"DEBUG: Response status: {response.status_code}")
    print(f"DEBUG: Response content: {response.text[:200]}...")
    return results
```

**File Processing Issues:**
```python
# Debug text processing
def make_tts_friendly(text: str) -> str:
    print(f"DEBUG: Input length: {len(text)}")
    processed = process_text(text)
    print(f"DEBUG: Output length: {len(processed)}")
    return processed
```

## Performance Profiling

### Basic Profiling

```python
import cProfile
import pstats
from wikibee import extract_wikipedia_text

# Profile extraction
cProfile.run('extract_wikipedia_text("Machine Learning")', 'profile_stats')

# Analyze results
stats = pstats.Stats('profile_stats')
stats.sort_stats('cumulative').print_stats(10)
```

### Memory Profiling

```python
from memory_profiler import profile

@profile
def test_large_article():
    text, title = extract_wikipedia_text("Very Long Article")
    return len(text)

# Run with: python -m memory_profiler script.py
```

## IDE Configuration

### VS Code

Recommended `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["-v"],
    "editor.rulers": [88],
    "files.trimTrailingWhitespace": true,
    "files.insertFinalNewline": true
}
```

### PyCharm

1. **Interpreter**: Point to `.venv/bin/python`
2. **Code Style**: Set line length to 88
3. **Testing**: Configure pytest as test runner
4. **Linting**: Enable ruff integration

## Troubleshooting Development Issues

### Virtual Environment Issues

```bash
# Recreate virtual environment
rm -rf .venv
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Import Errors

```bash
# Ensure package is installed in development mode
pip install -e .

# Check Python path
python -c "import sys; print(sys.path)"
```

### Test Failures

```bash
# Run tests with more verbose output
pytest -vvv --tb=long

# Run single failing test
pytest tests/test_specific.py::test_function_name -vvv

# Update test snapshots if needed
pytest --update-snapshots  # If using snapshot testing
```

### Pre-commit Issues

```bash
# Update hooks
pre-commit autoupdate

# Clear hook cache
pre-commit clean

# Reinstall hooks
pre-commit uninstall
pre-commit install
```

## Making Changes

### Workflow

1. **Create feature branch**: `git checkout -b feature/new-feature`
2. **Make changes**: Edit code following standards
3. **Add tests**: Ensure new functionality is tested
4. **Run tests**: `pytest -q`
5. **Check style**: `ruff check .`
6. **Commit changes**: `git commit -m "feat: add new feature"`
7. **Push and create PR**: `git push origin feature/new-feature`

### Commit Message Format

Use conventional commits:

```bash
# Types: feat, fix, docs, style, refactor, test, chore
git commit -m "feat: add search result limiting"
git commit -m "fix: handle unicode encoding in article titles"
git commit -m "docs: update API documentation"
git commit -m "test: add edge case tests for client"
```

## Release Process

For maintainers:

```bash
# Update version in pyproject.toml
# Update CHANGELOG.md
# Run full test suite
pytest

# Build package
uv build

# Tag release
git tag v0.1.1
git push origin v0.1.1

# Upload to PyPI (maintainers only)
uv run twine upload dist/*
```

---

**Navigation**: [Documentation Home](../README.md) | [Contributing](../../CONTRIBUTING.md) | [Testing Guide](testing.md) | [Architecture](architecture.md)
