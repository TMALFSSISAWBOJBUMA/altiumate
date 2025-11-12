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

import psutil
from humanize import naturaldelta as human_time

from altiumate.config import ALTIUMATE_VERSION, DEFAULT_RUN_TIMEOUT, sample_config_yaml


def eopen(
    file: str,
    mode: str = "r",
    errors: str | None = None,
):
    return open(file, mode, encoding="utf_8", errors=errors)


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


def subparsers_names(parser: argparse.ArgumentParser) -> list[str]:
    return list(parser._subparsers._group_actions[0]._name_parser_map.keys())


def read_altium_path():
    """Reads the path to Altium Designer executable from .altium_exe file.

    Raises:
        FileNotFoundError: If the file is missing

    Returns:
        pl.Path: path to AD executable read from file
    """
    try:
        with eopen(altiumate_dir / ".altium_exe") as f:
            altium_exe = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError("AD path file missing!")
    return pl.Path(altium_exe)


def find_altium_process() -> pl.Path | None:
    """Finds the X2.exe process in the process list.

    Returns:
        pl.Path|None: Path to Altium Designer executable if found, else None
    """
    for p in psutil.process_iter(["name", "exe"]):
        if "x2.exe" == p.name().lower():
            return pl.Path(p.exe())
    return None


def get_altium_path(
    version: str | None = None,
):  # TODO: maybe add 'latest' as an option
    """Returns the path to Altium Designer executable.

    If version is specified, executable will be selected using string matching, else \
        the already opened or the first instance found in Windows registry will be returned.\
        'any' can be used as a version placehoder.

    Raises:
        FileNotFoundError: If the registry key or specified version of AD is missing
        WindowsError: If the registry access fails

    Returns:
        pl.Path: Path to Altium Designer executable
    """
    if version == "any":
        version = None

    if version is None:
        path = find_altium_process()
        if path:
            return path

    fail = FileNotFoundError("Altium Designer is not installed on this computer")
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
                f"Multiple versions found for '{version}': {filtered}. Provide more specific version"
            )
        return installs[filtered[0]]
    for ver in installs:
        return installs[ver]


def add_project_path(parser: argparse.ArgumentParser):
    parser.add_argument(
        "project_path",
        help="Altium project file to use, defaults to first found in cwd",
        type=pl.Path,
        default=next(pl.Path.cwd().glob("*.PrjPcb"), None),
        nargs=argparse.OPTIONAL,
    )


def render_constants(
    call_procedure: str = "test_altiumate", terminate: bool = False, **params: str
):
    """Renders the altiumate.pas file with the provided parameters.

    call_procedure: str: Internals of the function that will be called. ';' is appended after this text if needed. Defaults to "test_altiumate"
    terminate: bool: Whether to terminate AD after script execution. Defaults to False
    params: dict[str, str]: Parameters to render in the altiumate.pas file as constants
    """
    AD_return_file.unlink(True)
    if call_procedure[-1] != ";":
        call_procedure += ";"
    with eopen(altiumate_dir / "AD_scripting" / "altiumate.pas", "w") as f_dst:
        header = (
            f"Const\n{'\n'.join(f"  {k} = '{v}';" for k, v in params.items())}\n"
            if params
            else ""
        )

        f_dst.write(
            f"""{header}Var
  return_code: integer;

Procedure RunFromAltiumate;
Var
  tmp_file: TextFile;
Begin
  return_code := 1;
  AssignFile(tmp_file, '{AD_return_file.as_posix()}');
  Try
    {call_procedure}
  Finally
    ReWrite(tmp_file);
    WriteLn(tmp_file, return_code);
    CloseFile(tmp_file);
  end;
  {"TerminateWithExitCode(return_code);" if terminate else ""}
End;
"""
        )


def _register_pre_commit(parser: argparse.ArgumentParser):
    ex_group: argparse._MutuallyExclusiveGroup = parser.add_mutually_exclusive_group()
    ex_group.add_argument(
        "--sample-config",
        help="Prints the contents of a sample pre-commit configuration file. Defaults to remote (using github link) config. Local config requires altiumate being in PATH",
        choices=["remote", "local"],
        const="remote",
        nargs=argparse.OPTIONAL,
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
        logger.info(f"Printing {args.print_config} config")
        print(sample_config_yaml(args.print_config))
        return 0
    elif args.add_config_file or args.add_linked_config:
        dir_to_add: pl.Path = args.add_config_file or args.add_linked_config

        if not dir_to_add.is_dir():
            return logger.error(f"Provided path {dir_to_add} is not a directory")
        out = dir_to_add / ".pre-commit-config.yaml"
        if out.exists() and not args.force:
            return logger.error(
                f"Config file {out} already exists. Use --force to overwrite"
            )

        if args.add_config_file:
            logger.info(f"Creating pre-commit config file in {dir_to_add}")
            with eopen(args.add_config_file / ".pre-commit-config.yaml", "w") as f:
                f.write(sample_config_yaml("remote"))
        else:
            conf = altiumate_dir / ".linked-config.yaml"
            if not conf.exists():
                logger.info(
                    f"Creating config file for linking in {altiumate_dir}. All linked configs will point to this file"
                )
                with eopen(conf, "w") as f:
                    f.write(sample_config_yaml("local"))
            out.unlink(True)
            logger.info(f"Creating hard link to {conf} in {dir_to_add}")
            return out.hardlink_to(conf)

        return logger.info(f"Pre-commit config file created in {dir}")
    elif args.install:
        logger.info("Running 'pre-commit install' command")
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


def _register_run(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--altium-version",
        help="Uses specific version of AD",
        dest="AD_version",
        type=str,
    )
    parser.add_argument(
        "--timeout",
        help=f"Timeout for AD script runtime in seconds. Defaults to {human_time(DEFAULT_RUN_TIMEOUT)}",
        dest="timeout",
        default=DEFAULT_RUN_TIMEOUT,
    )
    parser.add_argument(
        "--terminate",
        help="Terminate AD after script execution",
        action="store_true",
        dest="terminate",
    )

    subparsers = parser.add_subparsers(dest="run_cmd")

    sp = subparsers.add_parser(
        "procedure", help="Runs arbitrary code in AD Scripting System"
    )
    sp.add_argument(
        "procedure",
        help="Procedure to call in AD or a DelphiScript code snippet",
        metavar="procedure_or_code",
    )
    sp.add_argument(
        "file",
        type=pl.Path,
        nargs=argparse.ZERO_OR_MORE,
        help="Files to run in Altium Designer. Available in `passed_files` as a comma-separated list",
    )

    sp = subparsers.add_parser(
        "outjob", help="Runs an Output Job from a specified project"
    )
    add_project_path(sp)
    sp.add_argument(
        "-name",
        dest="outjob_name",
        metavar="outjob_name",
        help="OutJob file name to use. If not set, first OutJob found in project will be used",
        nargs=argparse.OPTIONAL,
    )

    sp = subparsers.add_parser(
        "unsaved-check", help="Checks for unsaved (modified) files in the project"
    )
    add_project_path(sp)


def file_exists(f: pl.Path) -> pl.Path:
    return f and f.exists() and f.is_file()


def _handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    altium = get_altium_path(args.AD_version)
    if args.run_cmd not in subparsers_names(parser):
        parser.error("Provide a command to run")

    parser = get_subparser(parser, args.run_cmd)
    if args.run_cmd == "procedure":
        if not (args.procedure or len(args.file) > 0):
            parser.error(
                "Provide a procedure name or files to pass to test_altiumate script"
            )
        logger.info(f"Changed files: {args.file}")
        f_ext = {f.suffix for f in args.file}
        logger.debug(f"Modified extensions: {f_ext}")

        render_constants(
            passed_files=",".join(str(f.absolute()) for f in args.file),
            call_procedure=args.procedure or "test_altiumate",
            terminate=args.terminate,
        )
    elif not file_exists(
        args.project_path
    ):  # project_path is required for other commands
        parser.error("Project file not found")
    if args.run_cmd == "outjob":
        if args.outjob_name:
            to_run = f"outjob_run_all('{args.project_path.absolute()}', '{args.outjob_name}')"
        else:
            to_run = f"outjob_run_all('{args.project_path.absolute()}')"
        to_run += ";\nreturn_code := 0;"

        render_constants(
            call_procedure=to_run,
            terminate=args.terminate,
        )

    elif args.run_cmd == "unsaved-check":
        if find_altium_process() is None:
            logger.warning("AD is not running, all files are considered saved")
            return 0

        render_constants(
            call_procedure=f"if modified_docs_in_project('{args.project_path.absolute()}')<>true then return_code := 0;",
            terminate=args.terminate,
        )

    cmd = f"{altium} -RScriptingSystem:RunScript(ProjectName={(altiumate_dir / 'AD_scripting' / 'precommit.PrjScr').absolute()}|ProcName=altiumate.pas>RunFromAltiumate)"

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

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,  # More secure
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
        raise TimeoutError(
            "AD took too long! Try setting a higher timeout with --timeout option"
        )
    logger.info(f"Task took {human_time(time.time() - proc_start)}")

    with eopen(AD_return_file) as fp:
        code = fp.readline()
        try:
            int(code)
        except Exception:
            logger.error(f"Invalid return code: {code}")
            return 1
        return int(code)


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
    with eopen(prjpcb) as f:

        def f_iter(f):
            for line in f:
                yield line.splitlines()[0]

        f_i = f_iter(f)
        check = re.compile(r"\[Parameter[0-9]")
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

            if check.match(line):  # Check for parameter section
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
    with eopen(readme) as f:
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
    with eopen(readme, "w") as f:
        f.write(data)
    logger.info(f"Updated {readme} with {inserted} parameters")
    return 0


def _register_readme(parser: argparse.ArgumentParser):
    add_project_path(parser)
    parser.add_argument(
        "readme_md",
        help="README.md to update, defaults to README.md in cwd",
        type=pl.Path,
        default=pl.Path("README.md"),
        nargs=argparse.OPTIONAL,
    )


def _handle_readme(args: argparse.Namespace, parser: argparse.ArgumentParser):
    file_exists(args.project_path) or parser.error(
        "No project file found. Add -h for help"
    )
    file_exists(args.readme_md) or parser.error(
        "No README.md file found. Add -h for help"
    )
    params = parse_prjpcb_params(args.project_path)
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
    parser.add_argument(
        "--version",
        help="Prints Altiumate version",
        dest="altiumate_version",
        action="store_true",
    )

    ad_grp = parser.add_argument_group("AD executable")
    ad_grp.add_argument(
        "--altium-path",
        help="Prints the path to Altium Designer executable with specified \
            version. If not specified, the first version found is returned",
        dest="altium_path",
        metavar="version",
        nargs=argparse.OPTIONAL,
        type=str,
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
        if args.altiumate_version:
            print(ALTIUMATE_VERSION)
            return 0
        elif args.altium_path:
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
            f"Check log file {(altiumate_dir / '.altiumate.log').absolute()} for more details"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
