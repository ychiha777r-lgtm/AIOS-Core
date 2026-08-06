#!/usr/bin/env bash
set -euo pipefail

mkdir -p .github/workflows
cat > .github/workflows/tests.yml <<'YAML'
name: CI - Tests
on:
  push:
    branches:
      - main
      - develop
      - 'feature/*'
  pull_request:
    branches:
      - main
      - develop

env:
  PYTHONUNBUFFERED: '1'

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [ '3.12.x' ]
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: |
            ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f "pyproject.toml" ]; then
            pip install -e ".[dev]" || pip install pytest pytest-asyncio coverage
          else
            pip install pytest pytest-asyncio coverage
          fi

      - name: Run pytest with coverage
        run: |
          mkdir -p reports
          coverage run -m pytest --junitxml=reports/junit.xml
          coverage xml -o reports/coverage.xml
          coverage html -d reports/htmlcov

      - name: Upload pytest report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pytest-report
          path: reports/junit.xml

      - name: Upload coverage report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: reports

      - name: Enforce minimum coverage
        run: |
          python - <<'PY'
import xml.etree.ElementTree as ET
import sys
try:
    tree = ET.parse('reports/coverage.xml')
except Exception:
    print('Could not parse reports/coverage.xml')
    sys.exit(1)
root = tree.getroot()
line_rate = root.attrib.get('line-rate')
if line_rate is None:
    print('Could not determine coverage from reports/coverage.xml')
    sys.exit(1)
coverage_percent = float(line_rate) * 100.0
print(f'Coverage: {coverage_percent:.2f}%')
if coverage_percent < 95.0:
    print('Coverage below threshold (95%)')
    sys.exit(2)
PY
YAML

git add .github/workflows/tests.yml
git commit -m "ci: add github actions test workflow"

echo "Workflow created at .github/workflows/tests.yml"
