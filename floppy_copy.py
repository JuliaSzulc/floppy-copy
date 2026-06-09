#!/bin/python3

import argparse
import datetime
import logging
import os
import pathlib
import shutil


def find_pictures(source_dir_path: pathlib.Path) -> list[pathlib.Path]:
    """
    Detects and lists pictures found on the floppy disk.

    Args:
        source_dir_path: Disk directory path

    Returns:
        List of paths to detected pictures
    """
    pictures_paths = (
        list(source_dir_path.glob("*.jpg", case_sensitive=False))
        + list(source_dir_path.glob("*.mpg", case_sensitive=False))
    )
    logging.info(f"{len(pictures_paths)} pictures found")

    return pictures_paths


def create_target_filenames(
    target_dir_path: pathlib.Path,
    pictures_paths: list[pathlib.Path],
) -> dict[pathlib.Path, str]:
    """
    Creates alternative target names of files ('YYMMDD_hhmmss'). Handles duplicates.

    Args:
        target_dir_path: Target directory where pictures are copied.
        pictures_paths: Source paths of pictures on the floppy disk.

    Returns:
        Dictionary of source paths mapped to their new filenames with extensions
    """
    def extract_timestamp(path: pathlib.Path) -> str:
        """
        Extracts last modification time of the file and formats it as YYMMDD_hhmmss.

        Args:
            path: Path to the file

        Returns:
            Name of the new file (formatted timestamp)
        """
        try:
            file_mtime = path.stat().st_mtime
        except (AttributeError, OSError) as e:
            raise RuntimeError(
                f"Metadata of {path} does not include required timestamp"
            ) from e

        return datetime.datetime.fromtimestamp(file_mtime).strftime("%y%m%d_%H%M%S")

    new_names: dict[pathlib.Path, str] = {}

    for filepath in pictures_paths:
        timestamp = extract_timestamp(filepath)
        extension = filepath.suffix
        new_filename = f"{timestamp}{extension}"

        i = 0
        while (
            (target_dir_path / new_filename).exists()
            or new_filename in new_names.values()
        ):
            i += 1
            new_filename = f"{timestamp}_{i}{extension}"

        new_names[filepath] = new_filename

    return new_names


def copy_files(
    target_filenames: dict[pathlib.Path, str],
    target_dir_path: pathlib.Path,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """
    Copies detected pictures from the floppy disk to the target path under new names.
    Ensures files are owned by the original user, even if the script is run with sudo.

    Args:
        target_filenames: Dictionary of source paths mapped to their new filenames
        target_dir_path: Target directory where pictures are copied.

    Returns:
        Two lists - one with successfully copied paths and other with failures.
    """
    success_paths: list[pathlib.Path] = []
    fail_paths: list[pathlib.Path] = []

    # Determine the real user's UID/GID (not root)
    user_uid = int(os.environ.get("SUDO_UID", os.getuid()))
    user_gid = int(os.environ.get("SUDO_GID", os.getgid()))

    for filepath, new_name in target_filenames.items():
        new_path = target_dir_path / new_name
        try:
            success_paths.append(shutil.copy2(filepath, new_path))

            # Dynamically restore ownership to the original user if run as root
            if os.geteuid() == 0:
                try:
                    os.chown(new_path, user_uid, user_gid)
                except OSError as e:
                    logging.warning(f"Could not set ownership for {new_path}: {e}")

        except Exception as e:
            logging.error(f"Failed to copy {filepath}: {e}")
            fail_paths.append(filepath)

    logging.info(
        f"Successfully copied {len(success_paths)}/{len(target_filenames)} files."
    )

    if fail_paths:
        logging.error(f"Failed to copy {len(fail_paths)}/{len(target_filenames)} files")
        for path in fail_paths:
            logging.error(f"  - {path}")

    return success_paths, fail_paths


def wipe_disk(disk_path: pathlib.Path) -> None:
    """
    Removes all files recursively from the target directory.

    Args:
        disk_path: Path to the disk directory
    """
    files_to_remove = [str(path) for path in disk_path.glob("*")]
    logging.warning(f"Everything in {disk_path} will be removed.")
    logging.warning(f"Files to remove:\n" + "\n".join(files_to_remove))

    if input("Type 'yes' to continue: ").lower() == "yes":
        for path in disk_path.glob("*"):
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                logging.info(f"{path} removed")
            except Exception as e:
                logging.error(f"Failed to remove {path}: {e}")
        logging.info("Files have been removed successfully.")
    else:
        logging.info("Nothing has been removed.")


def parse_args():
    def _correct_path(path: str) -> pathlib.Path:
        """
        Wrapper for path arguments type.

        Args:
            path: Input path.

        Raises:
            FileNotFoundError: If path does not exist or is not a directory.

        Returns:
            Unchanged input path
        """
        path = pathlib.Path(path)

        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")
        if not path.is_dir():
            raise FileNotFoundError(f"{path} is not a directory")
        return path

    parser = argparse.ArgumentParser(
        description="""
        Copy pictures taken with Sony Mavica camera from the floppy disk to your computer.

        The script uses file metadata to rename target files with a timestamp of last
        modification in a format `YYMMDD_hhmmss`. If more files (also in the target
        directory) have the same timestamp the suffix `_i` is added, where `i` is the number
        of the copy.

        By default the script does not clear the floppy after successfully copying files.
        When you run it with `--wipe` (`-w`) flag, make sure you review the list of files to
        be deleted, which is displayed before the removal.""",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "source",
        type=_correct_path,
        help="Path to the mounted floppy drive"
    )

    parser.add_argument(
        "target",
        type=_correct_path,
        help="Target directory for the pictures"
    )

    parser.add_argument(
        "-w",
        "--wipe",
        action='store_true',
        help="Wipe all data from the floppy after copying the files"
    )

    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

    args = parse_args()

    source_dir_path = args.source
    target_dir_path = args.target
    wipe_flag = args.wipe

    if wipe_flag and os.geteuid() != 0:
        raise PermissionError(
            "To wipe the floppy disk, the script must be run with root privileges. "
            "Run again with `sudo`"
        )

    pictures_paths = find_pictures(source_dir_path)

    if not pictures_paths:
        logging.info("No pictures found on the source disk. Exiting.")
        exit(0)

    target_filenames = create_target_filenames(target_dir_path, pictures_paths)

    _, fail_paths = copy_files(target_filenames, target_dir_path)

    if wipe_flag:
        if fail_paths:
            logging.warning("Aborting wiping the disk - some files were not copied")
        else:
            wipe_disk(source_dir_path)
