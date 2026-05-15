"""
Module: lyricsovh.py
Purpose: A simple thread-safe module to fetch song lyrics using the Lyrics.ovh API.
It queries the external service with a song name and artist, returns either found lyrics or an error status.
The function is designed to be used in multi-threaded environments (e.g., concurrent lyric fetching).
"""

from threading import current_thread
import logging
import requests

# Module-level identifier for logging purposes
provider_name = (
    __name__  # This will be '__main__' if run directly, or the module name otherwise
)


def get_lyrics(
    song_name: str,
    song_artist: str,
    song_duration: int,
    original_file_path: str,
) -> tuple[str, str | None]:
    """
    Fetches lyrics for a given song from the Lyrics.ovh API.

    This function sends an HTTP GET request to the Lyrics.ovh service using the provided
    song name and artist. It returns either:
        - ("OK", lyrics_text): If lyrics are successfully retrieved.
        - ("404", None): If the song is not found in the database.
        - (None, None): In case of any unexpected error during execution.

    Args:
        song_name (str): The name of the song (e.g., "Blinding Lights").
        song_artist (str): The name of the artist (e.g., "The Weeknd").
        song_duration (int): Duration of the song in seconds. Used for potential future filtering or metadata.
        original_file_path (str): Path to the original audio file. May be used for logging context.

    Returns:
        tuple[str, str | None]: A two-element tuple where:
            - First element is a status code ("OK" or "404").
            - Second element is either the lyrics text (if found) or None.

    Note:
        - The function uses thread-local information via `current_thread().name` for logging context.
        - It logs detailed messages at INFO and DEBUG levels, including success/failure states.
        - If an exception occurs during API call, it logs the error and returns (None, None).
        - The song duration parameter is currently unused in this implementation but may be used later.

    Example:
        >>> status, lyrics = get_lyrics("Blinding Lights", "The Weeknd", 234, "/path/to/song.mp3")
        >>> if status == "OK":
        ...     print(lyrics)
    """

    # Get the current thread's name for context in logs (useful in multi-threaded apps)
    thread_name = current_thread().name

    # Construct the API endpoint URL using the song artist and title
    # Format: https://api.lyrics.ovh/v1/{artist}/{song}
    Endpoint = f"https://api.lyrics.ovh/v1/{song_artist}/{song_name}"

    try:
        # Log the start of the request with thread context and input details
        logging.info(
            f'{thread_name} {provider_name}: 🔍 Querying lyrics for "{song_name}" by "{song_artist}"...'
        )

        # Perform GET request to Lyrics.ovh API
        Response = requests.get(Endpoint)

        # Check if the response was successful (HTTP 200 OK)
        if Response.status_code == 200:
            # Parse JSON response and extract lyrics from the result
            lyrics_data = Response.json()
            lyrics = lyrics_data["lyrics"]

            # Log success message with file path context
            logging.info(
                f'{thread_name} {provider_name}: 🌟 Lyrics for "{song_name}" by "{song_artist}" in file "{original_file_path}" found'
            )

            # Optional debug output: show the actual lyrics (useful during development)
            logging.debug(f"{thread_name} {provider_name}: Lyrics:\n{lyrics}")

            # Return success status and the retrieved lyrics
            return "OK", lyrics

        else:
            # Song not found or invalid request — log accordingly
            logging.info(
                f'{thread_name} {provider_name}: ❌ Song "{song_name}" by "{song_artist}" was not found'
            )

            # Return failure status and None lyrics
            return "404", None

    except Exception as error:
        # Catch any unexpected exceptions (network issues, malformed input, etc.)
        logging.error(
            f'{thread_name} {provider_name}: Can\'t get lyrics for "{song_name}" by "{song_artist}" due to: {error}'
        )

        # Return failure status and None in case of error
        return None, None


# End of module
