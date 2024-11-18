import argparse
import logging as log
import pathlib as pl
import subprocess
import winreg as wr

altiumate_dir = pl.Path(__file__).parent

log.basicConfig(
    level=log.NOTSET,
    format="%(asctime)s | %(levelname)s: %(message)s",
    handlers=[
        log.FileHandler((pl.Path.cwd() / "altiumate.log"), mode="w"),
        log.StreamHandler(),
    ],
)
log.getLogger().handlers[0].setLevel(log.DEBUG)
log.getLogger().handlers[1].setLevel(log.WARNING)


def read_altium_path():
    try:
        with open(altiumate_dir / ".altium_exe") as f:
            altium_exe = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError("AD path file missing!")
    return pl.Path(altium_exe)


def get_altium_path():
    fail = FileNotFoundError("Altium Designer is not installed on this computer.")
    try:
        with wr.OpenKey(
            wr.HKEY_LOCAL_MACHINE, "SOFTWARE\\Altium\\Builds"
        ) as key, wr.OpenKey(key, wr.EnumKey(key, 0)) as subkey:
            install_path = wr.QueryValueEx(subkey, "ProgramsInstallPath")[0]
            return pl.Path(install_path) / "X2.exe"
    except FileNotFoundError as e:
        log.critical("AD registry key not found.")
        raise fail from e
    except WindowsError as e:
        log.critical("Registry access failed! {e}")
        raise fail from e


def sample_config() -> str:
    return f"""fail_fast: true
repos:
  - repo: local
    hooks:
      - id: find-altium
        name: Find AD installation
        entry: {(altiumate_dir/"find_altium.bat").as_posix()}
        language: system
        always_run: true
      - id: generate-docs
        name: Generate Documentation
        entry: py {pl.Path(__file__).as_posix()} run
        language: system
        files: \\.(PrjPcb|SchDoc|PcbDoc)$
        description: "Generates documentation for the project"
"""


def render_constants(**params: str):
    with open(altiumate_dir / "inputs.pas", "w") as f_dst:
        data = "\n".join(f"\t{k} = '{v}';" for k, v in params.items())
        f_dst.write(f"const\n{data}\n")


def handle_pre_commit(args, parser):
    if args.print_config:
        return print(sample_config())
    if args.add_config_file:
        with open(args.add_config_file / ".pre-commit-config.yaml", "w") as f:
            f.write(sample_config())
        return log.info(f"Pre-commit config file created in {args.add_config_file}")
    if args.add_linked_config:
        conf = altiumate_dir / ".linked-config.yaml"
        if not conf.exists():
            with open(conf, "w") as f:
                f.write(sample_config())
        out: pl.Path = args.add_linked_config / ".pre-commit-config.yaml"
        out.unlink(True)
        return out.hardlink_to(conf)
    if args.install:
        proc: subprocess.CompletedProcess = subprocess.run(
            "pre-commit install",
            capture_output=True,
            text=True,
        )
        print(proc.stdout.rstrip())
        return proc.stderr and log.error(proc.stderr.rstrip())

    parser.print_help()


def main():
    parser = argparse.ArgumentParser(
        description="Altiumate - Altium Designer automation interface"
    )
    parser.add_argument(
        "--altium-path",
        help="Prints the path to Altium Designer executable",
        action="store_true",
        dest="altium_path",
    )
    subparsers = parser.add_subparsers(dest="cmd")
    pre = subparsers.add_parser("pre-commit", help="Pre-commit handling commands")
    pre.add_argument(
        "--sample-config",
        help="Prints the contents of a sample pre-commit configuration file",
        action="store_true",
        dest="print_config",
    )
    pre.add_argument(
        "--add-config",
        help="Adds pre-commit config to the directory",
        type=pl.Path,
        metavar="DIR",
        dest="add_config_file",
        nargs="?",
    )
    pre.add_argument(
        "--add-linked-config",
        help="Adds a symlink to altiumate sample config file to the directory",
        dest="add_linked_config",
        metavar="DIR",
        type=pl.Path,
        nargs="?",
    )
    pre.add_argument(
        "--install",
        help="Installs pre-commit hooks",
        action="store_true",
        dest="install",
    )
    run = subparsers.add_parser("run", help="Run scripts in Altium Designer")
    run.add_argument("file", type=pl.Path, nargs="+")
    args = parser.parse_args()
    if args.altium_path:
        return print(get_altium_path())
    elif args.cmd == "pre-commit":
        return handle_pre_commit(args, pre)
    elif args.cmd == "run":
        pass
    else:
        return parser.print_help()
    log.info(f"Changed files: {args.file}")
    f_ext = {f.suffix for f in args.file}
    log.info(f"Modified extensions: {f_ext}")

    altium = read_altium_path()

    render_constants(
        document_path=next(
            x for x in args.file if x.suffix in (".SchDoc", ".PcbDoc")
        ).absolute()
    )

    cmd = f"{altium} -RScriptingSystem:RunScript(ProjectName={(altiumate_dir/'precommit.PrjScr').absolute()}|ProcName=generate_outputs.pas>RunFromAltiumate)"
    proc: subprocess.CompletedProcess = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.exception(e)
        exit(1)
    exit(1)
