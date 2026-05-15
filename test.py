import os
import importlib.util
from pathlib import Path
from typing import Dict, Any


def load_providers_modules() -> Dict[str, Any]:
    """
    Load all Python files from the 'providers' directory in the same folder as this script.

    Returns:
        A dictionary where keys are the module names (without .py extension)
        and values are the imported modules.
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
            print(f"Could not create spec for {module_name}")
            continue

        # Load the module
        try:
            module = importlib.util.module_from_spec(spec)

            # Execute the module code
            spec.loader.exec_module(module)

            # Store in dictionary
            loaded_modules[module_name] = module

        except Exception as e:
            print(f"Error loading module {module_name}: {e}")
            continue

    return loaded_modules


# Example usage:
if __name__ == "__main__":
    try:
        providers_dict = load_providers_modules()

        # Now you can access modules like this:
        # provider_module = providers_dict["my_provider"]
        # result = provider_module.some_function()

        print(f"Loaded {len(providers_dict)} modules successfully.")

    except Exception as e:
        print(f"Error: {e}")
