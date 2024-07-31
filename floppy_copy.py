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
    pictures_paths = list(source_dir_path.glob("*.jpg", case_sensitive=False))
    logging.info(f"{len(pictures_paths)} pictures found")

    return pictures_paths


def create_target_filenames(
    target_dir_path: pathlib.Path,
    pictures_paths: list[pathlib.Path],
) -> dict[pathlib.Path: str]:
    """
    Creates alternative target names of files ('YYMMDD_hhmmss'). Handles duplicates.

    Args:
        target_dir_path: Target directory where pictures are copied.
        pictures_paths: Source paths of pictures on the floppy disk.

    Returns:
        Dictionary of source paths mapped to their new filenames with extensions (not
            paths)
    """
    def extract_timestamp(path: pathlib.Path) -> str:
        """
        Extracts last modification time of the file and formats it as YYMMDD_hhmmss.

        Args:
            path: Path to the file

        Returns:
            name of the new file (formatted timestamp)
        """
        try:
            file_mtime = path.stat().st_mtime
        except AttributeError as e:
            e.add_note(f"Metadata of {path} does not include required timestamp")
            raise

        return datetime.datetime.fromtimestamp(file_mtime).strftime("%y%m%d_%H%M%S")

    target_dir_files = [path.name for path in target_dir_path.iterdir()]
    new_names = {}

    for filepath in pictures_paths:
        timestamp = extract_timestamp(filepath)
        extension = filepath.suffix
        new_filename = timestamp + extension

        i = 0
        while new_filename in new_names.values() or new_filename in target_dir_files:
            i += 1
            new_filename = f"{timestamp}_{i}{extension}"

        new_names[filepath] = new_filename

    return new_names


def copy_files(
    target_filenames: dict[pathlib.Path: str],
    target_dir_path: pathlib.Path,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """
    Copies detected pictures from the floppy disk to the target path under new names.

    Args:
        target_filenames: Dictionary of source paths mapped to their new filenames with
            extensions (not paths)
        target_dir_path: target_dir_path: Target directory where pictures are copied.

    Returns:
        Two lists - one with successfully copied paths and other with failures.
    """
    success_paths, fail_paths = [], []

    for filepath, new_name in target_filenames.items():
        try:
            success_paths.append(shutil.copy2(filepath, (target_dir_path / new_name)))
        except Exception as e:
            logging.error(e)
            fail_paths.append(filepath)

    logging.info(
        f"Successfully copied {len(success_paths)}/{len(target_filenames)} files:"
    )
    for path in success_paths:
        logging.info(path)

    if fail_paths:
        logging.error(
            f"Failed to copy {len(fail_paths)}/{len(target_filenames)} files:"
        )
        for path in fail_paths:
            logging.error(path)

    try:
        for path in success_paths:
            os.chown(path, 1000, 1000)
    except Exception as e:
        e.add_note("Could not set ownership to the target files, continuing anyway.")
        logging.warning(e)

    return success_paths, fail_paths


def wipe_disk(disk_path: pathlib.Path) -> None:
    """
    Removes all files recursively from the target directory.

    Args:
        disk_path: Path to the disk directory
    """
    logging.warning(f"Everything in {disk_path} will be removed.")
    logging.warning("Directory contents:")
    logging.warning(f"{"\n".join(os.listdir(disk_path))}")


    if input("Type 'yes' to continue: ").lower() == "yes":
        for path in disk_path.glob("*"):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                os.remove(path)
            logging.info(f"{path} removed")
        pass
    else:
        logging.info("Nothing has been removed")


def parse_args():
    def correct_path(path: str) -> pathlib.Path:
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
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "source",
        type=correct_path,
        help="Path to the mounted floppy drive"
    )

    parser.add_argument(
        "target",
        type=correct_path,
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
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

    args = parse_args()

    source_dir_path = args.source
    target_dir_path = args.target
    wipe_flag = args.wipe

    # Check for root privileges
    if wipe_flag and os.getuid() != 0:
        raise PermissionError(
            "To wipe the floppy disk the script has to be run with root privileges. " +
            "Try running again with `sudo`."
        )

    pictures_paths = find_pictures(source_dir_path)
    target_filenames = create_target_filenames(target_dir_path, pictures_paths)

    _, fail_paths = copy_files(target_filenames, target_dir_path)

    if wipe_flag:
        if fail_paths:
            logging.warning("Aborting wiping the disk - some files were not copied")
        else:
            wipe_disk(source_dir_path)
