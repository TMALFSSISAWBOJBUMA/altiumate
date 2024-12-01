![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FTMALFSSISAWBOJBUMA%2Faltiumate%2Frefs%2Fheads%2Fmaster%2Fpyproject.toml)

# altiumate

Interface for executing scripts in Altium Designer projects for automation

# Install

Install the altiumate module using your package manager of choice:

```
python -m pip install git+https://github.com/TMALFSSISAWBOJBUMA/altiumate.git@v0.2.0

uv pip install git+https://github.com/TMALFSSISAWBOJBUMA/altiumate.git@v0.2.0
```

To use git hooks, install [pre-commit](https://pre-commit.com/#install).

# Usage

Run in a Python 3 interpreter, as a CLI application (install through a package manager) or in a pre-commit hook. To see what's available use the help `altiumate -h`.

### Example use:

```
# in your Altium project repo root (with altiumate in PATH)
altiumate pre-commit --add-config
altiumate pre-commit install
altiumate run procedure "ShowInfo('Hello from altiumate!')"
```

To use altiumate in pre-commit config add the following to your config:

```
-   repo: https://github.com/TMALFSSISAWBOJBUMA/altiumate
    rev: v0.2.0
    hooks:
        -id: find-altium
        -id: altium-run
            args: [procedure, <your global procedure or code snippet to execute>]
        -id: update-readme
```

or if you're starting a new config run `altiumate pre-commit add-config` or use `altiumate pre-commit --sample-config`.
