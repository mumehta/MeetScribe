# Contributing to Meeting Transcriber

Thank you for your interest in contributing to the Meeting Transcriber project! This guide will help you get started with contributing.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Process](#development-process)
- [Code Review](#code-review)
- [Release Process](#release-process)

## Code of Conduct

Please be respectful and considerate in all interactions. By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/MeetScribe.git
   cd MeetScribe
   
   # Set up Python environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements-dev.txt
   ```

## Development Process

1. **Branch Naming**:
   - `feature/feature-name` for new features
   - `bugfix/description` for bug fixes
   - `docs/update` for documentation updates

2. **Commit Messages**:
   - Use the format: `[TYPE] Brief description`
   - Types: `FEAT`, `FIX`, `DOCS`, `STYLE`, `REFACTOR`, `TEST`
   - Example: `[FEAT] Add speaker diarization support`

3. **Code Standards**:
   - Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
   - Use type hints for all functions
   - Document public APIs with docstrings
   - Write unit tests for new features

## Submitting Changes

1. Push your changes to your fork
2. Open a Pull Request against the main branch
3. Ensure all tests pass
4. Update documentation as needed
5. I'll review your PR and provide feedback

## Release Process

1. Create a release branch: `release/vX.Y.Z`
2. Update version in `pyproject.toml`
3. Update CHANGELOG.md with release notes
4. Create a PR to merge into `main`
5. Tag the release: `git tag vX.Y.Z`
6. Push the tag: `git push origin vX.Y.Z`
