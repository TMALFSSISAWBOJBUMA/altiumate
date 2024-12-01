import argparse
import logging
import os
import pathlib as pl
import re
import subprocess
import sys
import time
import winreg as wr
from collections.abc import Sequence

from humanize import naturaldelta as human_time

altiumate_dir = pl.Path(__file__).parent
AD_return_file = altiumate_dir / "AD_out"

logger = logging.getLogger("altiumate")
logger.setLevel(logging.DEBUG)


class Formatter(logging.Formatter):
    """Custom formatter for logging messages with ANSI color codes"""

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


f_log = logging.FileHandler((altiumate_dir / ".altiumate.log"), mode="a")
f_log.setFormatter(logging.Formatter(Formatter.fmt))
logger.addHandler(f_log)

o_log = logging.StreamHandler()
o_log.setLevel(logging.WARN)
o_log.setFormatter(Formatter())
logger.addHandler(o_log)


def get_subparser(
    parser: argparse.ArgumentParser, name: str
) -> argparse.ArgumentParser:
    return parser._subparsers._group_actions[0]._name_parser_map[name]


def read_altium_path():
    """Reads the path to Altium Designer executable from .altium_exe file.

    Raises:
        FileNotFoundError: If the file is missing

    Returns:
        pl.Path: path to AD executable read from file
    """
    try:
        with open(altiumate_dir / ".altium_exe") as f:
            altium_exe = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError("AD path file missing!")
    return pl.Path(altium_exe)


def get_altium_path(
    version: str | None = None,
):  # TODO: maybe add 'latest' as an option
    """Returns the path to Altium Designer executable from Windows registry.    
    If version is specified, executable will be selected using string matching, else \
        the first instance found will be returned. 'any' can be used as a version placehoder.

    Raises:
        FileNotFoundError: If the registry key or specified version of AD is missing
        WindowsError: If the registry access fails

    Returns:
        pl.Path: Path to Altium Designer executable
    """
    fail = FileNotFoundError("Altium Designer is not installed on this computer")
    if version == "any":
        version = None
    installs = {}
    try:
        with wr.OpenKey(wr.HKEY_LOCAL_MACHINE, "SOFTWARE\\Altium\\Builds") as key:
            for i in range(wr.QueryInfoKey(key)[0]):
                with wr.OpenKey(key, wr.EnumKey(key, i)) as subkey:
                    installs[wr.QueryValueEx(subkey, "Version")[0]] = pl.Path(
                        wr.QueryValueEx(subkey, "ProgramsInstallPath")[0], "X2.exe"
                    )
    except FileNotFoundError as e:
        logger.critical("AD registry key not found")
        raise fail from e
    except WindowsError as e:
        logger.critical("Registry access failed! {e}")
        raise fail from e
    logger.info(f"Found Altium Designer installations: {installs}")
    if version:
        filtered = list(filter(lambda x: x.startswith(version), installs.keys()))
        if len(filtered) == 0:
            raise FileNotFoundError(f"Version '{version}' not found")
        elif len(filtered) > 1:
            raise FileNotFoundError(
                f"Multiple versions found for '{version}': {filtered}"
            )
        return installs[filtered[0]]
    for ver in installs:
        return installs[ver]


def sample_config() -> str:
    """Returns a sample pre-commit configuration file for an Altium Designer PCB project."""
    return """fail_fast: true
default_language_version:
    python: python3.12
repos:
  - repo: https://github.com/TMALFSSISAWBOJBUMA/altiumate
    rev: v0.1.2
    hooks:
      - id: find-altium
        args: [--version, 24.9.1]
      - id: altium-run
        args: [--procedure, "ShowInfo('Hello from Altiumate!')"]
      - id: update-readme
      
"""


def render_constants(**params: str):
    """Renders the altiumate.pas file with the provided parameters.

    params: dict[str, str]: Parameters to render in the altiumate.pas file as constants.
    └─> call_procedure: str: Internals of the function that will be called. ';' is appended after this text. Defaults to "test_altiumate"
    """
    AD_return_file.unlink(True)
    procedure = params.pop("call_procedure", "test_altiumate")
    with open(altiumate_dir / "AD_scripting" / "altiumate.pas", "w") as f_dst:
        data = "\n".join(f"  {k} = '{v}';" for k, v in params.items())
        f_dst.write(
            f"""const
{data}

Var
  return_code: cardinal;


Procedure RunFromAltiumate;
Var
  tmp_file: TextFile;
Begin
  return_code := 1;
  AssignFile(tmp_file, '{AD_return_file.as_posix()}');
  Try
  {procedure};
  Finally
    ReWrite(tmp_file);
    WriteLn(tmp_file, return_code);
    CloseFile(tmp_file);
  end;
End;
"""
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
        help="Adds a .pre-commit-config.yaml file to the DIR directory",
        type=pl.Path,
        metavar="DIR",
        dest="add_config_file",
        nargs=argparse.OPTIONAL,
        const=pl.Path.cwd(),
    )
    ex_group.add_argument(
        "--add-linked-config",
        help="Adds .pre-commit-config.yaml to the directory as a hard link to altiumate sample config file",
        dest="add_linked_config",
        metavar="DIR",
        type=pl.Path,
        nargs=argparse.OPTIONAL,
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
        print(sample_config())
        return 0
    elif args.add_config_file or args.add_linked_config:
        dir_to_add: pl.Path = args.add_config_file or args.add_linked_config
        out = dir_to_add / ".pre-commit-config.yaml"
        if not dir_to_add.is_dir():  # TODO: add option to append to existing config
            return logger.error(f"Provided path {dir_to_add} is not a directory")
        if out.exists() and not args.force:
            return logger.error(
                f"Config file {out} already exists. Use --force to overwrite"
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
        return 1


DEFAULT_RUN_TIMEOUT = 60.0


def _register_run(parser: argparse.ArgumentParser):
    parser.add_argument("--procedure", help="Procedure to call in AD", dest="procedure")
    parser.add_argument(
        "--altium-version", help="Uses specific version of AD", dest="AD_version"
    )
    parser.add_argument(
        "--timeout",
        help=f"Timeout for AD script runtime in seconds. Defaults to {human_time(DEFAULT_RUN_TIMEOUT)}",
        dest="timeout",
        default=DEFAULT_RUN_TIMEOUT,
    )
    parser.add_argument(
        "file",
        type=pl.Path,
        nargs=argparse.ZERO_OR_MORE,
        help="Files to run in Altium Designer. Available in `passed_files` as a comma-separated list",
    )


def file_exists(f: pl.Path) -> pl.Path:
    return f and f.exists() and f.is_file()


def _handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.procedure or len(args.file) > 0:
        logger.info(f"Changed files: {args.file}")
        f_ext = {f.suffix for f in args.file}
        logger.debug(f"Modified extensions: {f_ext}")

        altium = get_altium_path(args.AD_version)

        render_constants(
            passed_files=",".join(str(f.absolute()) for f in args.file),
            call_procedure=args.procedure or "test_altiumate",
        )

        cmd = f"{altium} -RScriptingSystem:RunScript(ProjectName={(altiumate_dir / "AD_scripting" / 'precommit.PrjScr').absolute()}|ProcName=altiumate.pas>RunFromAltiumate)"

        try:
            max_run_time = float(args.timeout)
        except Exception:
            logger.error(
                f"Invalid timeout value '{args.timeout}', using default {human_time(DEFAULT_RUN_TIMEOUT)} "
            )
            max_run_time = DEFAULT_RUN_TIMEOUT
        assert max_run_time > 3, "Timeout must be larger than 3 seconds"
        assert max_run_time < 3600, "Timeout must be less than 1 hour"

        proc_start = time.time()
        proc: subprocess.CompletedProcess = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max_run_time,
        )
        # if AD is already opened, the subprocess returns before the script has finished executing
        # solution is creating a file containing exit code from inside AD and waiting for it to appear in altiumate

        timeout = False
        while not (
            (  # file is created after ReWrite command in AD, wait a little to write to the file and close it
                AD_return_file.exists()
                and (time.time() - os.path.getmtime(AD_return_file)) > 0.1
            )
            or timeout
        ):
            timeout = (time.time() - proc_start) > max_run_time
            time.sleep(0.3)
        if timeout:
            raise TimeoutError("AD took too long!")
        logger.info(f"Task took {human_time(time.time() - proc_start)}")

        with open(AD_return_file) as fp:
            code = fp.readline()
            try:
                int(code)
            except Exception:
                logger.error(f"Invalid return code: {code}")
                return 1
            return int(code)
    else:
        parser.error(
            "Provide a procedure name or files to pass to test_altiumate script"
        )


def parse_prjpcb_params(
    prjpcb: pl.Path,
) -> dict[
    str, str
]:  # TODO: Move to state machine parsing, include project variants and system parameters
    """Parses the parameters from an Altium Designer project file.

    Returns:
        dict[str, str]: A dictionary of parameters found in the project file
    """
    logger.info(f"Reading parameters from {prjpcb}")
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
                name = next(f_i).split("=", 1)[1]
                out[name] = next(f_i).split("=", 1)[1]
    logger.debug(f"Parameters: {out}")
    return out


def update_readme(
    readme: pl.Path, parameters: dict[str, str], fail_on_missing=True
) -> int:
    """Updates the README.md file with the parameters from the Altium Designer project file.

    File will be parsed for the following pattern:
    \\[\\]\\(\\<project_parameter>)any previous text that will be replaced\\[](/)

    For example: \\[\\](ProjectName)ProjectName Parameter Value\\[](/)

    Parameters:
        readme: pl.Path: Path to the README.md file
        parameters: dict[str, str]: Parameters to insert into the README.md file
        fail_on_missing: bool: Raise an error if a parameter is not found in the project file

    Returns:
        int: 0 if successful

    """
    inserted = 0
    with open(readme) as f:
        data = f.read()
        insert_pattern = r"\[\]\((.*?)\)(.*?)\[\]\(/\)"

        def replacer(match):
            nonlocal inserted
            key = match.group(1)
            if key not in parameters:
                if fail_on_missing:
                    raise KeyError(f"Parameter {key} not found in the project")
                parameters[key] = key
            else:
                inserted += 1
            return f"[]({key}){parameters[key]}[](/)"

        data = re.sub(insert_pattern, replacer, data)
    with open(readme, "w") as f:
        f.write(data)
    logger.info(f"Updated {readme} with {inserted} parameters")
    return 0


def _register_readme(parser: argparse.ArgumentParser):
    parser.add_argument(
        "prjpcb",
        help="Altium .PrjPcb file with parameters, defaults to first found in cwd",
        type=pl.Path,
        default=next(pl.Path.cwd().glob("*.PrjPcb"), None),
        nargs=argparse.OPTIONAL,
    )
    parser.add_argument(
        "readme_md",
        help="README.md to update, defaults to README.md in cwd",
        type=pl.Path,
        default=pl.Path("README.md"),
        nargs=argparse.OPTIONAL,
    )


def _handle_readme(args: argparse.Namespace, parser: argparse.ArgumentParser):
    file_exists(args.prjpcb) or parser.error("No project file found. Add -h for help")
    file_exists(args.readme_md) or parser.error(
        "No README.md file found. Add -h for help"
    )
    params = parse_prjpcb_params(args.prjpcb)
    return update_readme(args.readme_md, params)


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="altiumate", description="Altiumate - Altium Designer automation interface"
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
    ad_grp = parser.add_argument_group("AD executable")
    ad_grp.add_argument(
        "--altium-path",
        help="Prints the path to Altium Designer executable with specified \
            version. If not specified, the first version found is returned",
        dest="altium_path",
        metavar="version",
        nargs=argparse.OPTIONAL,
        const="any",
    )
    subparsers = parser.add_subparsers(dest="cmd")

    entries = {}

    def subparser(name, subparsers: argparse._SubParsersAction, **kwargs):
        sp = subparsers.add_parser(name, **kwargs)
        entries[name] = sp
        add_verbose(sp)
        globals()[f"_register_{name.replace('-', '_')}"](sp)
        return sp

    subparser("pre-commit", subparsers, help="Pre-commit handling commands")
    subparser("run", subparsers, help="Run scripts in Altium Designer")
    subparser("readme", subparsers, help="Update README.md with AD project parameters")

    if len(argv) == 0:
        return parser.print_help()
    args = parser.parse_args(argv)

    if args.verbose:
        o_log.setLevel(logging.INFO)

    try:
        if args.altium_path:
            print(get_altium_path(args.altium_path))
            return 0
        elif args.cmd in entries:
            return globals()[f"_handle_{args.cmd.replace('-', '_')}"](
                args, entries[args.cmd]
            )
        else:
            raise NotImplementedError(
                f"Command {args.cmd} not implemented",
            )

    except KeyboardInterrupt:
        logger.error("Interrupted by user")
        return 1
    except Exception as e:
        logger.critical(str(e))
        logger.warning(
            f'Check log file {(altiumate_dir / ".altiumate.log").absolute()} for more details'
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
