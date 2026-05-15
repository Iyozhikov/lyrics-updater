import argparse
import importlib.util
import logging
import os
import taglib
import time
from pathlib import Path
from threading import Thread, current_thread

allowed_extensions = ["flac", "mp3", "ape"]
enabled_lyrics_providers = {}
store_lrc_online_as_embedded = False
overridden_artist_name = None


def is_allowed_file(file_path: str) -> bool:
    """
    Check if a file has an allowed audio extension.

    Args:
        file_path (str): Full path to the file to check

    Returns:
        bool: True if the file extension is one of flac, mp3, or ape; False otherwise
    """
    base_ext = os.path.splitext(file_path)[1].lower()[1:]
    return base_ext in allowed_extensions


def find_audio_files(directory: str) -> list[str]:
    """
    Recursively search for all MP3/FLAC/APE files (ignoring hidden files) in the given directory.

    Args:
        directory (str): Path to search (relative or absolute)

    Returns:
        List of full paths to matching audio files (case-insensitive extension check)
    """
    audio_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            # Skip hidden files (those starting with '.')
            if file.startswith("."):
                continue
            if is_allowed_file(file_path=file):
                full_path = os.path.join(root, file)
                audio_files.append(full_path)

    return audio_files


def work_with_lyrics_providers(
    song_name: str, song_artist: str, song_duration: int, original_file_path: str
) -> tuple[str, str | None]:
    """
    Attempt to fetch lyrics from enabled providers in sequence with retry logic.

    This function tries each enabled provider up to 3 times. If a provider returns "404" or fails due to SSL error,
    it will retry (with delay). On success ("OK"), it returns the result and lyrics.
    If all attempts fail, it returns ("404", None).

    Args:
        song_name (str): Name of the song
        song_artist (str): Artist name of the song
        song_duration (int): Duration of the song in seconds
        original_file_path (str): Full path to the original audio file

    Returns:
        tuple: (status_code, lyrics) where status_code is "OK", "404", or "SSL_ERROR"
               and lyrics is either a string or None depending on success.

    Note:
        - If SSL error occurs and max retries are reached, provider is skipped.
        - Thread name is logged for traceability.
    """
    max_tries = 3
    thread_name = current_thread().name
    try:
        for lyrics_provider in enabled_lyrics_providers:
            for i in range(max_tries):
                result, lyrics = enabled_lyrics_providers[lyrics_provider].get_lyrics(
                    song_name=song_name,
                    song_artist=song_artist,
                    song_duration=song_duration,
                    original_file_path=original_file_path,
                )
                if result == "OK":
                    return result, lyrics
                if result == "404":
                    break
                if result == "SSL_ERROR":
                    logging.warning(
                        f"{thread_name} {lyrics_provider} Got SSL error, retrying {i}"
                    )
                    time.sleep(2)
                if result == "SSL_ERROR" and i == max_tries:
                    logging.warning(
                        f"{thread_name} {lyrics_provider} Got SSL error, max retries reached, skipping current provider"
                    )
                    break
        # Return result as-is after all attempts, normally it will be "404", None
        return result, lyrics
    except Exception as error:
        logging.error(f"{thread_name} Can't process {song_duration} due to: {error}")
        raise


def process_music_file(file_path: str) -> None:
    """
    Process a single music file by extracting metadata, fetching lyrics (if available), and saving them externally.

    Steps:
    1. Validate the file extension
    2. Read audio tags using taglib to extract artist and title
    3. Fetch online lyrics via enabled providers with fallback logic
    4. Save external LRC file if lyrics are found
    5. Optionally embed lyrics into the music file metadata

    Args:
        file_path (str): Full path to the audio file to process

    Raises:
        Exception: If unable to read tags or process file due to errors
    """
    thread_name = current_thread().name
    if not is_allowed_file(file_path=file_path):
        logging.error(
            f"{thread_name} Unsupported file. Only { allowed_extensions.join(', ')} are allowed."
        )
    else:
        try:
            song = taglib.File(file_path)
            logging.info(f"{thread_name} 🔊 Processing file {file_path}")
            if song.tags.get("ALBUMARTIST"):
                if len(song.tags["ALBUMARTIST"]) > 0:
                    song_artist = song.tags["ALBUMARTIST"][0]
            elif len(song.tags["ARTIST"]) > 0:
                song_artist = song.tags["ARTIST"][0]
            else:
                raise Exception("Can't get artist from existing tags!")
            if len(song.tags["TITLE"]) > 0:
                song_name = song.tags["TITLE"][0]
            else:
                raise Exception("Can't get song title from existing tags!")
            if song.tags.get("LYRICS"):
                song_lyrics = song.tags["LYRICS"][0]
            else:
                song_lyrics = None
            logging.info(
                f'{thread_name} Song "{song_name}" by "{song_artist}" duration "{song.length}"s'
            )
            for k, v in song.tags.items():
                logging.debug(f"{thread_name} Found tag: {k} - {v}")
            if overridden_artist_name:
                song_artist = overridden_artist_name
            online_lrc_status, online_lyrics = work_with_lyrics_providers(
                song_name=song_name,
                song_artist=song_artist,
                song_duration=int(song.length),
                original_file_path=file_path,
            )
            if online_lrc_status == "OK":
                if song_lyrics and online_lyrics:
                    if song_lyrics == online_lyrics:
                        logging.info(
                            f"{thread_name} Embedded and online lyrics are the same"
                        )
                    else:
                        logging.info(
                            f"{thread_name} Embedded and online lyrics are different"
                        )
                if online_lyrics:
                    save_lrc_file(original_file_path=file_path, lyrics=online_lyrics)
                if online_lyrics and store_lrc_online_as_embedded:
                    logging.info(
                        f'{thread_name} 💬 Saving embedded lyrics to the music file "{file_path}"...'
                    )
                    song.tags["LYRICS"] = online_lyrics
                    song.save()
            logging.info(
                f'{thread_name} 🔈 Finished processing music file "{file_path}"'
            )
        except Exception as error:
            logging.error(
                f'{thread_name} Can\'t process music file "{file_path}" due to: {error}'
            )
            raise


def save_lrc_file(original_file_path: str, lyrics: str) -> None:
    """
    Save the provided lyrics into a separate .lrc file.

    Args:
        original_file_path (str): Full path to the original audio file
        lyrics (str): Lyrics content to write to file

    Note:
        - The output filename is derived by replacing the extension with ".lrc"
        - File is written in UTF-8 encoding
    """
    thread_name = current_thread().name
    output_path = os.path.splitext(original_file_path)[0] + ".lrc"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(lyrics)
    logging.info(f'{thread_name} 📖 Saved external lyrics to "{output_path}"')


def load_providers_modules() -> dict[str, object]:
    """
    Load all Python modules from the 'providers' directory in the same folder as this script.

    This function scans for .py files in a subdirectory named 'providers', imports them,
    and returns a dictionary mapping module names (without '.py') to their loaded objects.

    Returns:
        dict: Dictionary where keys are module names (e.g., "lrclibnet") and values are the imported modules

    Raises:
        FileNotFoundError: If the providers directory does not exist
        ValueError: If 'providers' is a file instead of a directory
    """
    # Get the directory of the current file (where this function is called from)
    current_file_dir = Path(__file__).parent
    # Define the path to providers directory
    providers_path = current_file_dir / "providers"
    # Check if providers directory exists
    if not providers_path.exists():
        raise FileNotFoundError(f"Providers directory not found at {providers_path}")
    # If it's a file, raise an error
    if providers_path.is_file():
        raise ValueError(f"'providers' is a file, not a directory: {providers_path}")
    # Dictionary to store loaded modules
    loaded_modules = {}
    # Iterate through all Python files in the providers directory
    for py_file in providers_path.glob("*.py"):
        # Extract module name (remove .py extension)
        module_name = py_file.stem
        # Create a spec using importlib.util
        spec = importlib.util.spec_from_file_location(module_name, py_file.absolute())
        if spec is None:
            logging.warning(f"Could not create spec for {module_name}")
            continue
        # Load the module
        try:
            module = importlib.util.module_from_spec(spec)
            # Execute the module code
            spec.loader.exec_module(module)
            # Store in dictionary
            loaded_modules[module_name] = module
        except Exception as e:
            logging.warning(f"Error loading module {module_name}: {e}")
            continue
    return loaded_modules


def process_audio_files_in_batches(directory: str, batch_size: int = 5) -> None:
    """
    Process audio files in batches of specified size using threads.

    Args:
        directory: Directory to search for audio files
        processor_func: Function to apply to each file (takes file path as argument)
        batch_size: Number of files to process together in one batch (default: 5)

    Returns:
        None (processes files asynchronously)
    """
    # Find all audio files
    audio_files = find_audio_files(directory)
    if not audio_files:
        logging.error(f"No audio files found in {directory}")
        return
    logging.info(
        f"Found {len(audio_files)} audio files. Processing in batches of {batch_size}..."
    )
    # Process files in batches
    for i in range(0, len(audio_files), batch_size):
        batch = audio_files[i : i + batch_size]
        # Create a thread for each file in the batch
        logging.info(f"Batch {i//batch_size + 1} started")
        threads = []
        for file_path in batch:
            thread_name = f"Batch-{i//batch_size+1}-File-{len(threads)+1}"
            thread = Thread(
                target=process_music_file, args=(file_path,), name=thread_name
            )
            threads.append(thread)
        # Start all threads in the batch
        for thread in threads:
            thread.start()
        # Wait for all threads in this batch to complete
        for thread in threads:
            thread.join()
        logging.info(
            f"Batch {i//batch_size + 1} completed (files {i+1} to {min(i+batch_size, len(audio_files))})"
        )


def main():
    global enabled_lyrics_providers
    global overridden_artist_name
    global store_lrc_online_as_embedded
    parser = argparse.ArgumentParser(description="Get lyrics for a music file")
    parser.add_argument(
        "--batch-size",
        type=int,
        required=False,
        default=5,
        help="Batch size, amount of files to be processed at once, Default: 5",
    )
    parser.add_argument(
        "--filename",
        required=False,
        help="Path to the music file (must be mp3 or flac)",
    )
    parser.add_argument(
        "--directory", type=str, required=False, help="Directory to search (must exist)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--enabled-providers",
        required=False,
        default="lrclibnet",
        help='Lyrics providers to use separated by coma, Example: "lrclibnet,lyricsovh". Default: lrclibnet',
    )
    parser.add_argument(
        "--show-providers",
        action="store_true",
        help="List available lyrics providers",
    )
    parser.add_argument(
        "--store",
        action="store_true",
        help="Store online lyrics as embedded in music file metadata",
    )
    parser.add_argument(
        "--override-artist", type=str, required=False, help="Override album artist name"
    )
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Load lyrics providersm, process providers cli options
    available_lyrics_providers = load_providers_modules()
    cli_enabled_lyrics_providers = args.enabled_providers.split(",")
    for item in cli_enabled_lyrics_providers:
        if item in available_lyrics_providers:
            enabled_lyrics_providers[item] = available_lyrics_providers[item]
        else:
            logging.warning(f"Lyrics provider {item} is not found and will be skipped!")
    logging.info(
        f"Will be used next lyrics providers: {",".join(item for item in enabled_lyrics_providers)}"
    )
    # Process command line options
    if args.show_providers:
        logging.info(
            f"Available lyrics providers: {",".join(item for item in available_lyrics_providers)}"
        )
    else:
        if args.override_artist:
            overridden_artist_name = args.override_artist
        if args.store:
            store_lrc_online_as_embedded = True
        if args.filename:
            process_music_file(file_path=args.filename)
        if args.directory:
            process_audio_files_in_batches(
                directory=args.directory, batch_size=args.batch_size
            )


if __name__ == "__main__":
    main()
