"""
Module: lrclibnet.py
Purpose: A lyrics retrieval module that uses the LrclibClient to fetch or search for song lyrics.
Supports two modes:
  - Normal mode (default): Retrieves full lyrics using track ID, artist name, and duration.
  - Search-only mode: Performs a search via query and returns results without saving.

This module is designed for use in multi-threaded environments where multiple requests may be made
concurrently. Thread context is preserved through logging for traceability.
"""

from lrclib import LrclibClient
from threading import current_thread
import logging

# Module-level identifier used in logs to distinguish this provider
provider_name = (
    __name__  # This will be '__main__' if run directly, or the module name otherwise
)


def get_lyrics(
    song_name: str,
    song_artist: str,
    song_duration: int,
    original_file_path: str,
    search_lrc_only: bool = False,
) -> tuple[str, str | None]:
    """
    Fetches or searches for lyrics using the LrclibClient based on input parameters.

    This function supports two modes:
      - If `search_lrc_only=True`: Performs a search query and prints results (returns None).
      - Otherwise: Attempts to retrieve full lyrics using song name, artist, and duration.
        Returns either ("OK", lyrics) if found, or error codes like "404" or "SSL_ERROR".

    Args:
        song_name (str): The title of the song (e.g., "Blinding Lights").
        song_artist (str): The name of the artist (e.g., "The Weeknd").
        song_duration (int): Duration of the song in seconds. Used to match tracks during retrieval.
        original_file_path (str): Path to the original audio file. Used for logging context.
        search_lrc_only (bool, optional): If True, performs a search without retrieving lyrics.
            Results are printed and no lyrics are returned. Defaults to False.

    Returns:
        tuple[str, str | None]: A two-element tuple where:
            - First element is a status code indicating success/failure:
                * "OK" → Lyrics successfully retrieved or instrumental detected
                * "404" → Song not found in database
                * "SSL_ERROR" → Network/SSL-related failure (e.g., connection timeout, EOF)
                * None → Unexpected error occurred
            - Second element is either the lyrics string or None.

    Notes:
        - The `song_duration` parameter may be used by LrclibClient to filter results.
        - If no lyrics are found but an instrumental track exists, returns "OK", None with a warning.
        - In search mode (`search_lrc_only=True`), the function prints each result and returns None.
        - Error handling includes specific checks for common network issues (e.g., connection aborts).
        - All logs include thread context via `current_thread().name`.

    Example:
        >>> status, lyrics = get_lyrics("Blinding Lights", "The Weeknd", 234, "/song.mp3")
        >>> if status == "OK":
        ...     print(lyrics)
        ...
        >>> # Search mode
        >>> status, _ = get_lyrics("Blinding Lights", "The Weeknd", 0, "/song.mp3", search_lrc_only=True)
    """

    # Get the current thread's name for logging and debugging context
    thread_name = current_thread().name

    # Create LrclibClient
    client = LrclibClient()

    try:
        if search_lrc_only:
            # Search mode: perform a query using song title and artist
            logging.info(
                f'{thread_name} {provider_name}: Searching lyrics for "{song_name}" by "{song_artist}"...'
            )

            # Execute the search via LrclibClient
            search_results = client.search(
                track_query=song_name, artist_name=song_artist
            )

            # Print each result (for debugging or user feedback)
            for search_result in search_results:
                logging.info(
                    f"{thread_name} {provider_name}: Search result:\n{search_result}"
                )

            # In search mode, no lyrics are returned — just return None to indicate no retrieval
            return None, None

        else:
            # Normal retrieval mode: fetch lyrics using song name, artist, and duration
            logging.info(
                f'{thread_name} {provider_name}: 🔍 Querying lyrics for "{song_name}" by "{song_artist}"...'
            )

            # Retrieve lyrics via LrclibClient with full parameters
            lrcs = client.get(
                id_name=song_name, artist_name=song_artist, duration=song_duration
            )

            try:
                # Check if lyrics exist in the response
                if lrcs.lyrics:
                    logging.info(
                        f'{thread_name} {provider_name}: 🌟 Lyrics for "{song_name}" by "{song_artist}" file "{original_file_path}" found'
                    )
                    logging.debug(
                        f"{thread_name} {provider_name}: Lyrics:\n{lrcs.lyrics}"
                    )
                    return "OK", lrcs.lyrics

                # Handle instrumental tracks (no lyrics)
                elif lrcs.instrumental:
                    logging.info(
                        f"{thread_name} {provider_name}: Instrumental track, no lyrics"
                    )
                    return "OK", None

                else:
                    # Unexpected case: no lyrics and not an instrumental
                    logging.warning(
                        f"{thread_name} {provider_name}: Weird situation, you should not see this!"
                    )
                    return None, None

            except Exception as save_error:
                # Catch any exception that occurs during the saving or processing of lyrics
                logging.error(
                    f"{thread_name} {provider_name}: Failed to save lyrics: {save_error}"
                )
                return None, None

    except Exception as error:
        # Handle general exceptions from LrclibClient (e.g., network issues)

        # Specific error checks based on error message content
        if " not found" in str(error).lower():
            logging.info(f"{thread_name} {provider_name}: ❌ {error}")
            return "404", None

        elif "UNEXPECTED_EOF_WHILE_READING" in str(error):
            logging.error(
                f'{thread_name} {provider_name}: Can\'t get lyrics for "{song_name}" by "{song_artist}" file "{original_file_path}" due to: {error}'
            )
            return "SSL_ERROR", ""

        elif "Connection aborted" in str(error):
            logging.error(
                f'{thread_name} {provider_name}: Can\'t get lyrics for "{song_name}" by "{song_artist}" file "{original_file_path}" due to: {error}'
            )
            return "SSL_ERROR", ""

        else:
            # Generic error fallback
            logging.error(
                f'{thread_name} {provider_name}: Can\'t get lyrics for "{song_name}" by "{song_artist}" file "{original_file_path}" due to: {error}'
            )
            return None, None


# End of module
