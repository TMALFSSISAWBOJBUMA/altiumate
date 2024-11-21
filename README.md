# altiumate

Interface for executing scripts in Altium Designer for automation

# Install

Download the repository to access the files. To use git hooks, install [pre-commit](https://pre-commit.com/#install).

# Usage

Run in a Python 3 interpreter (v3.12 tested). To see what's available use the help CLI `py altiumate.py -h`.

### Example use:

```
# in your Altium project repo root
py <path_to>altiumate.py pre-commit --add-config
pre-commit install
py <path_to>altiumate.py run --procedure "ShowInfo('Hello from altiumate!')"
```
