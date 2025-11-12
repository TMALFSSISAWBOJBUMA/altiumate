import re

import yaml

ALTIUMATE_VERSION = "v0.4.1"
DEFAULT_RUN_TIMEOUT = 60.0

_hooks = [
    {
        "id": "find-altium",
        "args": ["--version", "24.9.1"],
        "name": "Find AD installation",
        "entry": "altiumate --altium-path",
        "description": "Finds Altium Designer installations",
        "pass_filenames": False,
        "always_run": True,
        "verbose": True,
        "language": "system",
    },
    {
        "id": "altium-run",
        "args": ["procedure", "ShowInfo('Hello from Altiumate!')"],
        "name": "Run in AD",
        "entry": "altiumate run",
        "files": r"\.(PrjPcb|SchDoc|PcbDoc|OutJob)$",
        "description": "Runs a script in Altium Designer",
        "language": "system",
    },
    {
        "id": "update-readme",
        "args": [],
        "name": "Update README.md",
        "entry": "altiumate readme",
        "files": r"\.(PrjPcb|md)$",
        "pass_filenames": False,
        "description": "Updates the README.md file with requested project parameters",
        "language": "system",
    },
    {
        "id": "check-unsaved",
        "args": [],
        "name": "Force file saving before commit",
        "entry": "altiumate run unsaved-check",
        "description": "Ensures there are no unsaved changes in Altium Designer before committing",
        "pass_filenames": False,
        "always_run": True,
        "language": "system",
    },
]

_header = {
    # "fail_fast": True,
    "default_language_version": {"python": "python3.12"},
    "repos": [],
}

_repo_local = {"repo": "local", "hooks": _hooks}
_repo_remote = {
    "repo": "https://github.com/TMALFSSISAWBOJBUMA/altiumate",
    "rev": ALTIUMATE_VERSION,
    "hooks": [],
}


def dump_config(config: dict, **kwargs) -> str:
    """Dumps the pre-commit configuration to a YAML string"""
    fltr = r"\n\s*args:\s*\[\]|(?=\n|$)"
    return re.sub(
        fltr,
        "",
        yaml.dump(
            data=config,
            indent=2,
            sort_keys=False,
            default_flow_style=kwargs.pop("default_flow_style", None),
            **kwargs,
        ),
    )


def sample_config_yaml(_type: str) -> str:
    """Returns a sample pre-commit configuration file for an Altium Designer PCB project

    Args:
        _type (str): "remote" or "local"
    """
    conf = _header
    if _type == "remote":
        conf["repos"] = [_repo_remote]
        for hook in _hooks:
            part = {k: hook[k] for k in ("id", "args")}
            part["language"] = "python"
            conf["repos"][0]["hooks"].append(part)
        return dump_config(conf)
    elif _type == "local":
        conf = _header.copy()
        conf["repos"] = [_repo_local]
        return dump_config(conf)
    else:
        raise ValueError(f"Invalid type: {_type}")


def get_hooks_yaml():
    hooks = list()
    for hook in _hooks:
        part = {k: v for k, v in hook.items() if k not in ("args", "language")}
        part["language"] = "python"
        hooks.append(part)

    return dump_config(hooks, default_flow_style=False)


if __name__ == "__main__":
    with open(".pre-commit-hooks.yaml", "w") as f:
        f.write(get_hooks_yaml())
