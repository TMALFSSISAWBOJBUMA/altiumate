import argparse
import logging
import pathlib as pl
import re
import subprocess
import sys
import winreg as wr
from collections.abc import Sequence

altiumate_dir = pl.Path(__file__).parent

logger = logging.getLogger("altiumate")
logger.setLevel(logging.DEBUG)


class Formatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    turquoise = "\033[36;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: turquoise,
        logging.INFO: grey,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red,
    }

    def __fmt(self, lvl):
        return self.FORMATS.get(lvl, self.grey) + self.fmt + self.reset

    def format(self, record):
        self._style._fmt = self.__fmt(record.levelno)
        return super().format(record)


f_log = logging.FileHandler((altiumate_dir / ".altiumate.log"), mode="w")
f_log.setFormatter(logging.Formatter(Formatter.fmt))
logger.addHandler(f_log)

o_log = logging.StreamHandler()
o_log.setLevel(logging.WARN)
o_log.setFormatter(Formatter())
logger.addHandler(o_log)


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
        logger.critical("AD registry key not found.")
        raise fail from e
    except WindowsError as e:
        logger.critical("Registry access failed! {e}")
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
      - id: update-readme
        name: Update README.md
        entry: py {pl.Path(__file__).as_posix()} run readme
        language: system
        files: \\.(PrjPcb|md)$
        pass_filenames: false
        description: "Updates the README.md file with requested project parameters"
      
"""


def render_constants(**params: str):
    procedure = params.pop("call_procedure", "test_altiumate")
    with open(altiumate_dir / "altiumate.pas", "w") as f_dst:
        data = "\n".join(f"  {k} = '{v}';" for k, v in params.items())
        f_dst.write(
            f"const\n{data}\n\nProcedure RunFromAltiumate;\nBegin\n  {procedure};\nEnd;\n"
        )


def _register_pre_commit(parser: argparse.ArgumentParser):
    ex_group: argparse._MutuallyExclusiveGroup = parser.add_mutually_exclusive_group()
    ex_group.add_argument(
        "--sample-config",
        help="Prints the contents of a sample pre-commit configuration file",
        action="store_true",
        dest="print_config",
    )
    ex_group.add_argument(
        "--add-config",
        help="Adds pre-commit config to the directory",
        type=pl.Path,
        metavar="DIR",
        dest="add_config_file",
        nargs="?",
        const=pl.Path.cwd(),
    )
    ex_group.add_argument(
        "--add-linked-config",
        help="Adds a symlink to altiumate sample config file to the directory",
        dest="add_linked_config",
        metavar="DIR",
        type=pl.Path,
        nargs="?",
        const=pl.Path.cwd(),
    )
    ex_group.add_argument(
        "--install",
        help="Installs pre-commit hooks",
        action="store_true",
        dest="install",
    )
    parser.add_argument("--force", help="Force the operation", action="store_true")


def _handle_pre_commit(args: argparse.Namespace, parser: argparse.ArgumentParser):
    if args.print_config:
        return print(sample_config())
    elif args.add_config_file or args.add_linked_config:
        dir_to_add: pl.Path = args.add_config_file or args.add_linked_config
        out = dir_to_add / ".pre-commit-config.yaml"
        if not dir_to_add.is_dir():
            return logger.error(f"Provided path {dir_to_add} is not a directory.")
        if out.exists() and not args.force:
            return logger.error(
                f"Config file {out} already exists. Use --force to overwrite."
            )

        if args.add_config_file:
            with open(args.add_config_file / ".pre-commit-config.yaml", "w") as f:
                f.write(sample_config())
        else:
            conf = altiumate_dir / ".linked-config.yaml"
            if not conf.exists():
                with open(conf, "w") as f:
                    f.write(sample_config())
            out.unlink(True)
            return out.hardlink_to(conf)

        return logger.info(f"Pre-commit config file created in {dir}")
    elif args.install:
        proc: subprocess.CompletedProcess = subprocess.run(
            "pre-commit install",
            capture_output=True,
            text=True,
        )
        print(proc.stdout.rstrip())
        return proc.stderr and logger.error(proc.stderr.rstrip())
    else:
        parser.print_usage()


def parse_prjpcb_params(prjpcb: pl.Path) -> dict[str, str]:
    # reading = None
    # store = {}
    out = {}
    with open(prjpcb) as f:

        def f_iter(f):
            for line in f:
                yield line.splitlines()[0]

        f_i = f_iter(f)
        for line in f_i:
            # if reading is None:
            #     if '[' and line.endswith(']'):
            #         print(repr(line))
            #         reading = line.strip('[]')
            #         if reading.startswith('ProjectVariant'):
            #             reading = 'ProjectVariant'
            #             store = {'Description': None, 'ParameterCount': None}
            #         break
            # else:
            #     if not line and reading != 'ProjectVariant' or all(store.values()):
            #         reading = None
            #     if reading == 'Design':
            #         out.update([line.split('=', 1)])

            if "[Parameter" in line:  # Check for parameter section
                print(repr(line))
                name = next(f_i).split("=", 1)[1]
                out[name] = next(f_i).split("=", 1)[1]
    return out


def update_readme(readme: pl.Path, parameters: dict[str, str]):
    with open(readme) as f:
        data = f.read()
        insert_pattern = r"\[\]\((.*?)\)(.*?)\[\]\(/\)"

        def replacer(match):
            key = match.group(1)
            if key not in parameters:
                raise KeyError(f"Parameter {key} not found in the project.")
            return f"[]({key}){parameters[key]}[](/)"

        data = re.sub(insert_pattern, replacer, data)
    with open(readme, "w") as f:
        f.write(data)
    return 0


def _register_run(parser: argparse.ArgumentParser):
    ridmi = parser.add_subparsers(dest="subcmd").add_parser(
        "readme", help="Handles updating the readme file with Altium project parameters"
    )
    ridmi.add_argument(
        "--project",
        help="Altium .PrjPcb file with parameters",
        dest="project_path",
        type=pl.Path,
        default=next(pl.Path.cwd().glob("*.PrjPcb"), None),
    )
    ridmi.add_argument(
        "--readme_file",
        help="README.md",
        dest="readme",
        type=pl.Path,
        default=pl.Path("README.md"),
    )
    parser.add_argument("--procedure", help="Procedure to call in AD", dest="procedure")
    parser.add_argument(
        "file",
        type=pl.Path,
        nargs="*",
        help="Files to run in Altium Designer. Available in `passed_files` as a comma-separated list.",
    )


def _handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser):
    # args.file: Sequence[pl.Path]
    if args.subcmd == "readme":
        return update_readme(args.readme, parse_prjpcb_params(args.project_path))
    if args.procedure or len(args.file) > 0:
        logger.info(f"Changed files: {args.file}")
        f_ext = {f.suffix for f in args.file}
        logger.debug(f"Modified extensions: {f_ext}")

        altium = read_altium_path()

        render_constants(
            passed_files=",".join(str(f.absolute()) for f in args.file),
            call_procedure=args.procedure or "test_altiumate",
        )

        cmd = f"{altium} -RScriptingSystem:RunScript(ProjectName={(altiumate_dir/'precommit.PrjScr').absolute()}|ProcName=altiumate.pas>RunFromAltiumate)"
        proc: subprocess.CompletedProcess = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    else:
        parser.error(
            "Provide a procedure name or files to pass to test_altiumate script."
        )


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Altiumate - Altium Designer automation interface"
    )

    def add_verbose(parser):
        parser.add_argument(
            "-v",
            "--verbose",
            help="Increase verbosity",
            action="store_true",
            dest="verbose",
        )

    add_verbose(parser)
    parser.add_argument(
        "--altium-path",
        help="Prints the path to Altium Designer executable",
        action="store_true",
        dest="altium_path",
    )
    subparsers = parser.add_subparsers(dest="cmd")

    entries = {}

    def subparser(name, subparsers: argparse._SubParsersAction, **kwargs):
        sp = subparsers.add_parser(name, **kwargs)
        entries[name] = sp
        # add_verbose(sp)
        globals()[f"_register_{name.replace('-', '_')}"](sp)
        return sp

    subparser("pre-commit", subparsers, help="Pre-commit handling commands")
    subparser("run", subparsers, help="Run scripts in Altium Designer")

    if len(argv) == 0:
        return parser.print_help()
    args = parser.parse_args(argv)

    if args.verbose:
        o_log.setLevel(logging.DEBUG)

    try:
        if args.altium_path:
            return print(get_altium_path())

        elif args.cmd in entries:
            return globals()[f"_handle_{args.cmd.replace('-', '_')}"](
                args, entries[args.cmd]
            )
        else:
            raise NotImplementedError(
                f"Command {args.cmd} not implemented.",
            )

    except Exception as e:
        logger.critical(str(e))
        exit(1)


if __name__ == "__main__":
    exit(main())
